"""Regression cho `setup_shared_root.py` — Router V3.2.

Bài quyết định: bản sao bare phải THẬT SỰ cập nhật khi chạy lại, không chỉ
báo "ok". `git clone --bare` không tự đặt refspec fetch, nên `git fetch
--all` sau đó tải object mới nhưng KHÔNG cập nhật `main` cục bộ — bản sao
đứng yên ở commit lúc clone trong khi báo thành công. Phát hiện khi bản
sao bare dùng cho AG02 vẫn đứng ở commit trước PR #111 dù đã "cập nhật".
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.router_v3 import setup_shared_root as ssr

#: icacls cần một tài khoản Windows THẬT để /grant thành công, nhưng KHÔNG
#: phải tài khoản đang chạy — nó chắc chắn đã có mặt trong ACL hồ sơ chính
#: của chính nó, làm `kiem_ho_so_chinh` báo vấn đề giả. `Guest` là tài khoản
#: cục bộ có sẵn trên mọi máy Windows và không đụng hồ sơ của ai.
_TK_THAT = "Guest"


def _git(cwd: Path, *args) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", "-C", str(cwd), *args],
                       capture_output=True, text=True, check=True)
    return r


def _tip(cwd: Path, ref: str = "main") -> str:
    return _git(cwd, "log", "-1", "--format=%H", ref).stdout.strip()


class CapNhatBanSaoBareTest(unittest.TestCase):
    """Chạy lại `setup_shared_root.main()` phải kéo commit MỚI vào bare."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rv32-ssr-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "--quiet", "-b", "main")
        _git(self.repo, "config", "user.email", "t@t.test")
        _git(self.repo, "config", "user.name", "t")
        (self.repo / "a.txt").write_text("1", encoding="utf-8")
        _git(self.repo, "add", "a.txt")
        _git(self.repo, "commit", "-q", "-m", "đầu")

        self.goc = self.tmp / "shared"

    def test_chay_lai_keo_duoc_commit_moi_vao_main_cua_bare(self):
        rc = ssr.main(["--root", str(self.goc), "--accounts", _TK_THAT,
                       "--repo", str(self.repo)])
        self.assertEqual(rc, 0)
        bare = self.goc / ssr.MIRROR
        tip_dau = _tip(bare)
        self.assertEqual(tip_dau, _tip(self.repo))

        (self.repo / "a.txt").write_text("2", encoding="utf-8")
        _git(self.repo, "add", "a.txt")
        _git(self.repo, "commit", "-q", "-m", "commit thứ hai")
        moi_o_nguon = _tip(self.repo)
        self.assertNotEqual(moi_o_nguon, tip_dau)

        rc2 = ssr.main(["--root", str(self.goc), "--accounts", _TK_THAT,
                        "--repo", str(self.repo)])
        self.assertEqual(rc2, 0)

        # Bai quyet dinh: TRUOC fix, `main` cua bare van dung o `tip_dau`
        # du lenh fetch bao thoat ma 0.
        self.assertEqual(
            _tip(bare), moi_o_nguon,
            "bản sao bare KHÔNG cập nhật main dù chạy lại — commit mới bị bỏ sót")

    def test_refspec_fetch_duoc_dat_tuong_minh_tren_bare(self):
        ssr.main(["--root", str(self.goc), "--accounts", _TK_THAT,
                  "--repo", str(self.repo)])
        bare = self.goc / ssr.MIRROR
        r = _git(bare, "config", "--get", "remote.origin.fetch")
        self.assertIn("refs/heads/*:refs/heads/*", r.stdout)


if __name__ == "__main__":
    unittest.main()
