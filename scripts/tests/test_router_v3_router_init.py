"""`router init <repo>` — Router LTS Phase 13.

Bài quyết định: chạy trên một kho TẠM (không phải kho thật của dự án này)
— lệnh này không được đụng vào bất kỳ bí mật/tệp nào của dự án gọi nó.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3 import router_init as ri


class DungThuMucTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rv-init-"))
        subprocess.run(["git", "init", "--quiet"], cwd=self.tmp, check=True)

    def test_tao_du_5_thu_muc_con(self):
        kq = ri.dung(self.tmp)
        for ten in ri.THU_MUC_CON:
            self.assertTrue((self.tmp / ".router" / ten).is_dir())

    def test_tao_config_mac_dinh_hop_le(self):
        ri.dung(self.tmp)
        cfg = json.loads((self.tmp / ".router" / "config" / "config.json")
                         .read_text(encoding="utf-8"))
        self.assertIn("speed_mode", cfg)

    def test_them_dong_gitignore_neu_chua_co(self):
        (self.tmp / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        ri.dung(self.tmp)
        noi_dung = (self.tmp / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".router/", noi_dung)
        self.assertIn("node_modules/", noi_dung)   # khong xoa dong cu

    def test_tao_gitignore_moi_neu_chua_co(self):
        ri.dung(self.tmp)
        self.assertTrue((self.tmp / ".gitignore").exists())
        self.assertIn(".router/", (self.tmp / ".gitignore").read_text(encoding="utf-8"))

    def test_chay_lai_KHONG_ghi_de_config_da_co(self):
        ri.dung(self.tmp)
        tep = self.tmp / ".router" / "config" / "config.json"
        tep.write_text('{"speed_mode": "safe", "tuy_chinh": true}', encoding="utf-8")
        kq2 = ri.dung(self.tmp)
        cfg = json.loads(tep.read_text(encoding="utf-8"))
        self.assertTrue(cfg.get("tuy_chinh"))
        self.assertIn(str(tep), kq2["đã_có"])

    def test_force_config_ghi_de(self):
        ri.dung(self.tmp)
        tep = self.tmp / ".router" / "config" / "config.json"
        tep.write_text('{"tuy_chinh": true}', encoding="utf-8")
        ri.dung(self.tmp, ghi_de_cau_hinh=True)
        cfg = json.loads(tep.read_text(encoding="utf-8"))
        self.assertNotIn("tuy_chinh", cfg)

    def test_chay_lai_khong_tao_trung(self):
        ri.dung(self.tmp)
        ri.dung(self.tmp)
        noi_dung = (self.tmp / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(noi_dung.count(".router/"), 1)

    def test_KHONG_dung_gi_ngoai_thu_muc_muc_tieu(self):
        """Bai quyet dinh: chi tao ben trong goc du an duoc chi dinh."""
        truoc = set(self.tmp.parent.iterdir())
        ri.dung(self.tmp)
        sau = set(self.tmp.parent.iterdir())
        self.assertEqual(truoc, sau)


class MainCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rv-init-cli-"))
        subprocess.run(["git", "init", "--quiet"], cwd=self.tmp, check=True)

    def test_main_thanh_cong_tren_kho_git_that(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = ri.main([str(self.tmp)])
        self.assertEqual(rc, 0)
        self.assertTrue((self.tmp / ".router" / "worktrees").is_dir())

    def test_main_bao_loi_neu_duong_dan_khong_phai_thu_muc(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = ri.main([str(self.tmp / "khong-ton-tai")])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
