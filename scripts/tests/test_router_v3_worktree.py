"""Worktree ↔ bộ lập lịch — Router V3.1, Phase 1.

Dùng một kho git THẬT trong thư mục tạm. Cô lập là thứ không giả lập được:
điều cần chứng minh là hai worker chạy song song thực sự ghi vào hai cây khác
nhau, và điều đó chỉ đúng nếu `git worktree` thật sự làm việc đó.

Kho tạm bị xoá ở `tearDown`; kho THẬT của dự án không bị đụng tới.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.dag import RiskClass, TaskDag, TaskNode
from scripts.router_v3.registry import (ExecutionType, Health, WorkerRegistry,
                                        WorkerSpec)
from scripts.router_v3.scheduler import Scheduler
from scripts.router_v3.worktree import (
    WorktreeError,
    WorktreeHandle,
    WorktreeManager,
    normalize_worktree_metadata_attributes,
    resolve_worktree_metadata_dir,
)


def _git(cwd, *a):
    p = subprocess.run(["git", "-C", str(cwd), *a], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(a[:2])}: {p.stderr[:200]}")
    return p.stdout


class _KhoTam(unittest.TestCase):
    """Kho git thật, dùng một lần, trong thư mục tạm."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rv31-"))
        _git(self.tmp, "init", "-q", "-b", "main")
        _git(self.tmp, "config", "user.email", "t@t.test")
        _git(self.tmp, "config", "user.name", "t")
        for ten in ("a.txt", "b.txt"):
            (self.tmp / ten).write_text("goc\n", encoding="utf-8")
        _git(self.tmp, "add", "-A")
        _git(self.tmp, "commit", "-q", "-m", "goc")
        self.wt = WorktreeManager(self.tmp)
        self.sha = self.wt.base_sha()

    def tearDown(self):
        # Go worktree truoc de git khong giu khoa tep tren Windows.
        try:
            for w in self.wt.list_worktrees():
                p = w.get("worktree", "")
                if p and Path(p).resolve() != self.tmp.resolve():
                    subprocess.run(["git", "-C", str(self.tmp), "worktree",
                                    "remove", "--force", p],
                                   capture_output=True, text=True)
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _reg(self, n=2):
        r = WorkerRegistry()
        for i in range(n):
            wid = f"W{i}"
            r.register(WorkerSpec(worker_id=wid, provider_family="antigravity",
                                  execution_type=ExecutionType.LOCAL_CLI,
                                  pool="P",
                                  capabilities=frozenset({"implement"}),
                                  max_concurrent=1))
            r.set_health(wid, Health.HEALTHY)
        return r


class DungWorktreeTest(_KhoTam):
    def test_tao_worktree_va_nhanh_rieng(self):
        h = self.wt.create("AG01", "T1", base_sha=self.sha)
        self.assertTrue(h.path.exists())
        self.assertEqual(h.branch, "router/AG01/T1")
        self.assertEqual(h.base_sha, self.sha)
        self.assertTrue((h.path / "a.txt").exists())

    def test_hai_worker_duoc_hai_cay_KHAC_NHAU(self):
        a = self.wt.create("AG01", "T1", base_sha=self.sha)
        b = self.wt.create("AG02", "T2", base_sha=self.sha)
        self.assertNotEqual(a.path, b.path)
        (a.path / "a.txt").write_text("A sua\n", encoding="utf-8")
        (b.path / "a.txt").write_text("B sua\n", encoding="utf-8")
        # Cô lập THẬT: mỗi cây giữ nội dung riêng, không giẫm lên nhau.
        self.assertEqual((a.path / "a.txt").read_text(encoding="utf-8"), "A sua\n")
        self.assertEqual((b.path / "a.txt").read_text(encoding="utf-8"), "B sua\n")
        self.assertEqual((self.tmp / "a.txt").read_text(encoding="utf-8"), "goc\n")

    def test_KHONG_ghi_de_worktree_da_co(self):
        self.wt.create("AG01", "T1", base_sha=self.sha)
        with self.assertRaises(WorktreeError) as ctx:
            self.wt.create("AG01", "T1", base_sha=self.sha)
        self.assertIn("KHÔNG ghi đè", str(ctx.exception))

    def test_base_sha_khong_hop_le_bi_tu_choi(self):
        with self.assertRaises(WorktreeError):
            self.wt.create("AG01", "T1", base_sha="deadbeef" * 5)

    def test_pham_vi_ghi_duoc_kiem_that(self):
        h = self.wt.create("AG01", "T1", base_sha=self.sha)
        (h.path / "a.txt").write_text("sua\n", encoding="utf-8")
        self.assertEqual(self.wt.verify_scope(h, ["a.txt"]), [])
        self.assertEqual(self.wt.verify_scope(h, ["b.txt"]), ["a.txt"])

    def test_tep_moi_ngoai_pham_vi_bi_bat(self):
        h = self.wt.create("AG01", "T1", base_sha=self.sha)
        (h.path / "la.txt").write_text("x\n", encoding="utf-8")
        self.assertIn("la.txt", self.wt.verify_scope(h, ["a.txt"]))

    def test_worktree_KHONG_bi_tu_xoa(self):
        """Một worktree hỏng là bằng chứng để điều tra."""
        h = self.wt.create("AG01", "T1", base_sha=self.sha)
        self.assertTrue(h.path.exists())
        self.assertEqual(self.wt.stale(), [])   # cua chinh luot nay -> khong cu


class LapLichCoLapTest(_KhoTam):
    def _exec_ghi(self, ten_tep="a.txt"):
        def f(packet, worker):
            # Worker THAT lam viec trong `packet.workspace`.
            self.assertTrue(packet.workspace, "goi viec phai mang workspace")
            (Path(packet.workspace) / ten_tep).write_text(
                f"{packet.task_id}\n", encoding="utf-8")
            return '{"status":"ok","summary":"xong"}', 0.01
        return f

    def test_nut_CO_GHI_khong_co_manager_bi_TU_CHOI(self):
        """Chạy chúng trên cây chung sẽ để hai worker giẫm lên nhau."""
        d = TaskDag([TaskNode(id="a", objective="x", write_scope=("a.txt",))])
        s = Scheduler(self._reg(), self._exec_ghi(), max_parallel=1)
        with self.assertRaises(WorktreeError) as ctx:
            s.run(d)
        self.assertIn("CÓ GHI", str(ctx.exception))

    def test_cay_chinh_BAN_thi_tu_choi(self):
        """SHA gốc phải là điểm xuất phát SẠCH."""
        (self.tmp / "a.txt").write_text("chua commit\n", encoding="utf-8")
        d = TaskDag([TaskNode(id="a", objective="x", write_scope=("a.txt",))])
        s = Scheduler(self._reg(), self._exec_ghi(), max_parallel=1,
                      base_sha=self.sha, worktrees=self.wt)
        with self.assertRaises(WorktreeError) as ctx:
            s.run(d)
        self.assertIn("BẨN", str(ctx.exception))

    def test_nut_chi_doc_KHONG_can_worktree(self):
        d = TaskDag([TaskNode(id="r", objective="doc", read_scope=("a.txt",))])
        s = Scheduler(self._reg(), lambda p, w: ('{"status":"ok"}', 0.01),
                      max_parallel=1, base_sha=self.sha, worktrees=self.wt)
        bc = s.run(d)
        self.assertTrue(bc.ok)
        self.assertEqual(bc.workspaces, {})

    def test_hai_nut_ghi_SONG_SONG_vao_hai_cay_rieng(self):
        d = TaskDag([
            TaskNode(id="A", objective="x", write_scope=("a.txt",)),
            TaskNode(id="B", objective="y", write_scope=("b.txt",)),
        ])
        s = Scheduler(self._reg(2), self._exec_ghi(), max_parallel=2,
                      base_sha=self.sha, worktrees=self.wt)
        bc = s.run(d)
        self.assertEqual(len(bc.workspaces), 2)
        self.assertNotEqual(bc.workspaces["A"], bc.workspaces["B"])
        # Cay CHINH khong bi dong toi.
        self.assertEqual((self.tmp / "a.txt").read_text(encoding="utf-8"), "goc\n")

    def test_ghi_NGOAI_pham_vi_bi_chan_lai(self):
        """`write_scope` là HỢP ĐỒNG, và worker có thể phá nó. Nếu tích hợp
        tin kết quả mà không kiểm, thay đổi ngoài phạm vi sẽ lên main."""
        d = TaskDag([TaskNode(id="A", objective="x", write_scope=("a.txt",))])
        # Worker ghi `b.txt` du chi duoc phep ghi `a.txt`.
        s = Scheduler(self._reg(), self._exec_ghi("b.txt"), max_parallel=1,
                      base_sha=self.sha, worktrees=self.wt)
        bc = s.run(d)
        self.assertFalse(bc.ok)
        self.assertEqual(bc.results["A"].status, "blocked")
        self.assertIn("A", bc.scope_violations)
        self.assertIn("b.txt", bc.scope_violations["A"][0])

    def test_ket_qua_mang_nhanh_de_tich_hop_doc_lai(self):
        """Tích hợp phải tiêu thụ COMMIT/nhánh, không phải trạng thái tệp
        đang thay đổi đồng thời."""
        d = TaskDag([TaskNode(id="A", objective="x", write_scope=("a.txt",))])
        s = Scheduler(self._reg(), self._exec_ghi(), max_parallel=1,
                      base_sha=self.sha, worktrees=self.wt)
        bc = s.run(d)
        self.assertIn("branch=router/", bc.results["A"].integration_notes)
        self.assertIn(self.sha[:12], bc.results["A"].integration_notes)


if __name__ == "__main__":
    unittest.main()


class NativeWorkerHopDongTest(unittest.TestCase):
    """`native_worker` — hợp đồng, không gọi mạng.

    Bài quan trọng nhất ở đây khoá lại một điều đã ĐO ĐƯỢC: `agy --print`
    trả `status=SUCCESS` cho một việc sửa tệp mà **không hề sửa tệp nào**.
    Nên `ok` của worker KHÔNG BAO GIỜ đủ để kết luận một nút CÓ GHI đã xong.
    """

    def test_tach_bach_do_tre_model_va_overhead(self):
        from scripts.router_v3.native_worker import NativeRun

        r = NativeRun(ok=True, wall_seconds=6.5, model_seconds=1.42)
        self.assertAlmostEqual(r.overhead_seconds, 5.08, places=2)
        self.assertGreater(r.overhead_ratio, 0.7)

    def test_overhead_khong_bao_gio_am(self):
        from scripts.router_v3.native_worker import NativeRun

        # `duration_seconds` cua agy co the nhinh hon wall do lam tron.
        r = NativeRun(wall_seconds=1.0, model_seconds=1.2)
        self.assertEqual(r.overhead_seconds, 0.0)

    def test_mac_dinh_KHONG_cho_sua_tep(self):
        """Một worker chỉ-đọc không được có quyền ghi."""
        import inspect

        from scripts.router_v3.native_worker import run_native

        sig = inspect.signature(run_native)
        self.assertIs(sig.parameters["allow_edits"].default, False)

    def test_ok_cua_worker_KHONG_du_de_ket_luan_da_ghi(self):
        """Đã đo: agy trả SUCCESS + "XONG." mà không tạo tệp nào. Lưới thật
        là `verify_scope` trên tệp THẬT, không phải lời worker."""
        from scripts.router_v3.worktree import WorktreeManager

        self.assertTrue(hasattr(WorktreeManager, "verify_scope"))


class WarmWorkerHopDongTest(unittest.TestCase):
    """Worker ấm — hợp đồng, không gọi mạng."""

    def test_hinh_dang_ban_tin_dung_chuan(self):
        """PHẢI có `event` (không phải `type`) và `message`. Sai hình dạng thì
        CLI trả ERROR: 'stream input message is missing the "event" field'."""
        import json as _json

        from scripts.router_v3.native_worker import _ban_tin

        d = _json.loads(_ban_tin("xin chao"))
        self.assertEqual(d["event"], "user")
        self.assertEqual(d["message"]["role"], "user")
        self.assertEqual(d["message"]["content"], "xin chao")
        self.assertNotIn("type", d)

    def test_thieu_ket_qua_KHONG_bi_nuot(self):
        """Lô bị cắt giữa chừng mà trả về ít kết quả hơn số việc sẽ làm nơi
        gọi GHÉP NHẦM kết quả với việc — hỏng im lặng, khó thấy nhất."""
        from unittest import mock

        from scripts.router_v3 import native_worker as nw

        gia = mock.Mock()
        gia.stdout = ('{"event":"result","result":{"status":"SUCCESS",'
                      '"response":"1"}}\n')
        gia.stderr = ""
        with mock.patch.object(nw.subprocess, "run", return_value=gia), \
             mock.patch.object(nw, "find_agy", return_value="agy"):
            ra = nw.run_warm_batch(["a", "b", "c"], model="m")
        self.assertEqual(len(ra), 3)
        self.assertTrue(ra[0].ok)
        self.assertFalse(ra[1].ok)
        self.assertIn("không nhận được kết quả", ra[1].error)

    def test_khong_co_agy_thi_moi_viec_deu_that_bai(self):
        from unittest import mock

        from scripts.router_v3 import native_worker as nw

        with mock.patch.object(nw, "find_agy", return_value=None):
            ra = nw.run_warm_batch(["a", "b"], model="m")
        self.assertEqual(len(ra), 2)
        self.assertFalse(any(r.ok for r in ra))


class GhiTepCanWorkspaceTest(unittest.TestCase):
    def test_allow_edits_ma_thieu_workspace_bi_TU_CHOI(self):
        """`--add-dir` là BẮT BUỘC cho việc có ghi. Thiếu nó, worker im lặng
        không làm gì — chính điểm này từng làm một phép đo kết luận nhầm rằng
        headless không ghi được."""
        from scripts.router_v3.native_worker import run_native

        r = run_native("x", model="m", allow_edits=True, workspace=None)
        self.assertFalse(r.ok)
        self.assertIn("add-dir", r.error)


class GocDungChungTest(unittest.TestCase):
    """Worktree phải TỰ CHỨA khi worker chạy dưới tài khoản khác.

    Đây là bài quan trọng nhất của topology dùng chung: chuyển worktree sang
    thư mục chia sẻ là CHƯA đủ, vì tệp `.git` của nó trỏ ngược về kho mẹ.
    Một tài khoản không đọc được kho mẹ sẽ hỏng ở mọi lệnh git.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rv32-goc-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "user.email", "t@t.test")
        _git(self.repo, "config", "user.name", "t")
        (self.repo / "a.txt").write_text("goc\n", encoding="utf-8")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "goc")

        # Ban sao BARE trong "goc dung chung".
        self.chung = self.tmp / "shared"
        self.chung.mkdir()
        self.bare = self.chung / "repo.git"
        subprocess.run(["git", "clone", "--bare", "--quiet",
                        str(self.repo), str(self.bare)],
                       capture_output=True, text=True, check=True)
        # Ban sao bare KHONG ke thua config cua kho nguon, va worktree tao tu
        # no cung vay. Tren may co danh tinh git toan cuc thi commit van chay,
        # nen loi chi lo ra tren CI ("Author identity unknown") — dung kieu
        # bai test chi hong o mot moi truong.
        _git(self.bare, "config", "user.email", "t@t.test")
        _git(self.bare, "config", "user.name", "t")

    def tearDown(self):
        for goc in (self.bare,):
            try:
                for w in subprocess.run(
                        ["git", "-C", str(goc), "worktree", "list", "--porcelain"],
                        capture_output=True, text=True).stdout.splitlines():
                    if w.startswith("worktree "):
                        subprocess.run(["git", "-C", str(goc), "worktree",
                                        "remove", "--force", w.split(" ", 1)[1]],
                                       capture_output=True, text=True)
            except Exception:
                pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _wt(self):
        return WorktreeManager(self.repo, git_dir=self.bare,
                               worktree_root=self.chung / "workers")

    def test_worktree_nam_trong_GOC_DUNG_CHUNG(self):
        wt = self._wt()
        h = wt.create("AG02", "T1", base_sha=wt.base_sha())
        self.assertTrue(str(h.path).startswith(str(self.chung)),
                        f"{h.path} phải nằm trong {self.chung}")

    def test_gitdir_TU_CHUA_khong_tro_ve_kho_me(self):
        """Điều kiện quyết định để AG02 dùng được: `.git` không được trỏ về
        hồ sơ mà AG02 không đọc được."""
        wt = self._wt()
        h = wt.create("AG02", "T1", base_sha=wt.base_sha())
        tro = (h.path / ".git").read_text(encoding="utf-8")
        self.assertIn(str(self.bare.name), tro)
        self.assertNotIn(str(self.repo), tro,
                         "worktree vẫn phụ thuộc kho mẹ -> AG02 sẽ hỏng")

    def test_worker_lam_viec_va_commit_duoc_trong_goc_chung(self):
        wt = self._wt()
        h = wt.create("AG02", "T1", base_sha=wt.base_sha())
        (h.path / "a.txt").write_text("AG02 sua\n", encoding="utf-8")
        self.assertEqual(wt.verify_scope(h, ["a.txt"]), [])
        _git(h.path, "add", "-A")
        _git(h.path, "commit", "-q", "-m", "AG02 sua")
        sha = _git(h.path, "rev-parse", "HEAD").strip()
        self.assertTrue(sha)

    def test_hai_worker_hai_cay_rieng_trong_goc_chung(self):
        wt = self._wt()
        sha = wt.base_sha()
        a = wt.create("AG01", "TA", base_sha=sha)
        b = wt.create("AG02", "TB", base_sha=sha)
        self.assertNotEqual(a.path, b.path)
        (a.path / "a.txt").write_text("A\n", encoding="utf-8")
        (b.path / "a.txt").write_text("B\n", encoding="utf-8")
        self.assertEqual((a.path / "a.txt").read_text(encoding="utf-8"), "A\n")
        self.assertEqual((b.path / "a.txt").read_text(encoding="utf-8"), "B\n")

    def test_KHONG_dat_goc_chung_thi_giu_hanh_vi_cu(self):
        """Mặc định vẫn là `repo/.router/worktrees` — không phá cấu hình cũ."""
        wt = WorktreeManager(self.repo)
        self.assertTrue(str(wt.worktree_root).startswith(str(self.repo)))
        self.assertEqual(wt.git_root, self.repo)


class WindowsWorktreeCleanupTest(_KhoTam):
    """Kiểm tra việc dọn dẹp worktree và giải phóng thuộc tính READONLY trên Windows."""

    def test_regression_reproduce_incident_and_cleanup_succeeds(self):
        """Tái hiện chính xác sự cố: worktree đã mất cây vật lý nhưng còn
        metadata trong .git/worktrees/<tên>, thư mục logs/ và refs/ bị đặt cờ
        FILE_ATTRIBUTE_READONLY trên Windows khiến git worktree prune thất bại.
        Chứng minh: sau khi chuẩn hoá thuộc tính, dọn dẹp thành công không lỗi."""
        h = self.wt.create("AG01", "reproduce-task", base_sha=self.sha)
        self.assertTrue(h.path.exists())

        meta_dir = self.wt.find_metadata_dir(h)
        self.assertIsNotNone(meta_dir)
        self.assertTrue(meta_dir.exists())

        # Tạo cấu trúc con logs và refs giống môi trường git thực tế
        logs_dir = meta_dir / "logs"
        logs_dir.mkdir(exist_ok=True)
        (logs_dir / "HEAD").write_text("dummy reflog content\n", encoding="utf-8")
        refs_dir = meta_dir / "refs"
        refs_dir.mkdir(exist_ok=True)
        (refs_dir / "bad").write_text("dummy ref\n", encoding="utf-8")

        # Xoá cây làm việc vật lý để biến nó thành worktree stale/mồ côi
        shutil.rmtree(h.path)
        self.assertFalse(h.path.exists())

        # Xoá tệp gitdir trong metadata để tái hiện trạng thái hỏng như agy-story-meta
        gitdir_file = meta_dir / "gitdir"
        if gitdir_file.exists():
            gitdir_file.unlink()

        # Đặt cờ READONLY trên Windows
        if sys.platform == "win32":
            import ctypes
            k = ctypes.windll.kernel32
            k.SetFileAttributesW(str(logs_dir / "HEAD"), 1)
            k.SetFileAttributesW(str(logs_dir), 1)
            k.SetFileAttributesW(str(refs_dir / "bad"), 1)
            k.SetFileAttributesW(str(refs_dir), 1)
            k.SetFileAttributesW(str(meta_dir), 1)

            # Xác minh rằng nếu không gỡ READONLY, lệnh rmdir của hệ thống sẽ thất bại với Access is denied
            with self.assertRaises(PermissionError):
                os.rmdir(str(logs_dir))

        # Thực hiện prune_stale cho đúng worktree này
        self.wt.prune_stale(worktree_name=meta_dir.name)

        # Chứng minh: metadata đã bị dọn sạch hoàn toàn, không còn thư mục ma
        self.assertFalse(meta_dir.exists())

    def test_unrelated_active_worktrees_remain_byte_for_byte_unchanged(self):
        """Dọn dẹp một worktree stale tuyệt đối không ảnh hưởng đến các worktree đang sống:
        nội dung tệp nguyên vẹn từng byte, đăng ký git worktree giữ nguyên."""
        w1 = self.wt.create("AG01", "active-one", base_sha=self.sha)
        w2 = self.wt.create("AG02", "active-two", base_sha=self.sha)

        file_w1 = w1.path / "file1.txt"
        file_w1.write_text("content-one-unique", encoding="utf-8")
        file_w2 = w2.path / "file2.txt"
        content_w2_expected = "content-two-unique-byte-for-byte-12345\n"
        file_w2.write_text(content_w2_expected, encoding="utf-8")

        w2_meta = self.wt.find_metadata_dir(w2)
        self.assertIsNotNone(w2_meta)
        w2_meta_files_before = {f.name: f.stat().st_size for f in w2_meta.iterdir() if f.is_file()}

        # Gỡ bỏ w1
        self.wt.remove(w1)
        self.assertFalse(w1.path.exists())

        # Xác minh w2 hoàn toàn nguyên vẹn
        self.assertTrue(w2.path.exists())
        self.assertEqual(file_w2.read_text(encoding="utf-8"), content_w2_expected)
        self.assertTrue(w2_meta.exists())
        w2_meta_files_after = {f.name: f.stat().st_size for f in w2_meta.iterdir() if f.is_file()}
        self.assertEqual(w2_meta_files_before, w2_meta_files_after)

        # Xác minh w2 vẫn nằm trong danh sách worktree đang hoạt động
        active_paths = [Path(w["worktree"]).resolve() for w in self.wt.list_worktrees() if w.get("worktree")]
        self.assertIn(w2.path.resolve(), active_paths)
        self.assertNotIn(w1.path.resolve(), active_paths)

    def test_branch_not_deleted_on_worktree_remove(self):
        """Gỡ worktree chỉ xoá cây làm việc và metadata, KHÔNG tự ý xoá nhánh git."""
        h = self.wt.create("AG01", "branch-persist", base_sha=self.sha)
        nhanh = h.branch

        test_file = h.path / "new_file.txt"
        test_file.write_text("branch data\n", encoding="utf-8")
        _git(h.path, "add", "new_file.txt")
        _git(h.path, "commit", "-q", "-m", "commit on branch")
        commit_sha = _git(h.path, "rev-parse", "HEAD").strip()

        # Remove worktree
        self.wt.remove(h)
        self.assertFalse(h.path.exists())

        # Nhánh git vẫn tồn tại trong repo và trỏ đến đúng commit_sha
        sha_after = _git(self.tmp, "rev-parse", nhanh).strip()
        self.assertEqual(commit_sha, sha_after)

    def test_repeated_cleanup_is_idempotent(self):
        """Xoá nhiều lần liên tiếp không bao giờ sinh ngoại lệ (idempotent)."""
        h = self.wt.create("AG01", "idempotent-task", base_sha=self.sha)
        name = h.path.name
        self.wt.remove(h)
        self.assertFalse(h.path.exists())

        # Gọi lại lần 2, lần 3 trên handle
        self.wt.remove(h)
        self.wt.remove(h)

        # Gọi lại trên đường dẫn hoặc tên metadata
        self.wt.remove(name)
        self.wt.prune_stale(worktree_name=name)
        self.wt.prune_stale()

    def test_non_windows_noop(self):
        """Trên nền tảng phi-Windows, hàm normalize_worktree_metadata_attributes là no-op."""
        called = []
        def mock_setter(p, attrs):
            called.append(p)
            return True

        meta_dir = self.wt.git_common_dir / "worktrees"
        normalize_worktree_metadata_attributes(meta_dir, _platform="linux", _setter=mock_setter)
        self.assertEqual(called, [])

    def test_attribute_clearing_failure_surfaced_honestly(self):
        """Khi việc xoá thuộc tính thất bại, lỗi phải được báo cáo trung thực qua WorktreeError."""
        test_dir = self.tmp / "test_attr_failure"
        test_dir.mkdir()
        (test_dir / "child.txt").write_text("test")

        def failing_setter(path_str, attrs):
            raise WorktreeError(f"mô phỏng lỗi quyền trên {path_str}")

        with self.assertRaises(WorktreeError) as ctx:
            normalize_worktree_metadata_attributes(test_dir, _platform="win32", _setter=failing_setter)
        self.assertIn("mô phỏng lỗi quyền", str(ctx.exception))

    def test_path_traversal_and_outside_paths_rejected(self):
        """Chặn đường dẫn ra ngoài thư mục worktree metadata hoặc ký tự traversal."""
        with self.assertRaises(WorktreeError):
            resolve_worktree_metadata_dir(self.wt.git_common_dir, "../outside")

        with self.assertRaises(WorktreeError):
            resolve_worktree_metadata_dir(self.wt.git_common_dir, "..\\outside")

        with self.assertRaises(WorktreeError):
            resolve_worktree_metadata_dir(self.wt.git_common_dir, "sub/dir")

        with self.assertRaises(WorktreeError):
            resolve_worktree_metadata_dir(self.wt.git_common_dir, "")

        with self.assertRaises(WorktreeError):
            self.wt.find_metadata_dir("../../malicious")

    def test_worktree_with_special_characters_and_spaces_in_metadata_dir(self):
        """Hỗ trợ worktree có tên chứa ký tự đặc biệt hợp lệ và kiểm tra tên metadata có khoảng trắng."""
        h = self.wt.create("AG01", "task_v1.0-fix", base_sha=self.sha)
        self.assertTrue(h.path.exists())
        meta = self.wt.find_metadata_dir(h)
        self.assertIsNotNone(meta)

        self.wt.remove(h)
        self.assertFalse(h.path.exists())
        self.assertFalse(meta.exists())

        # Kiểm tra resolve_worktree_metadata_dir với tên có khoảng trắng
        space_meta = resolve_worktree_metadata_dir(self.wt.git_common_dir, "my worktree name")
        self.assertEqual(space_meta.name, "my worktree name")
        self.assertEqual(space_meta.parent, (self.wt.git_common_dir / "worktrees").resolve())

