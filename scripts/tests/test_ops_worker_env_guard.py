"""`--check` KHONG di qua rao chan `--require-env` — chan lai loi do sai duong.

Su co that (nghiem thu AWS staging, 2026-09-04):

    [FAIL] worker TU CHOI khi bi ep --require-env production — exit 0 (mong doi 2)

Bai kiem do chay `python -m server.worker --require-env production --check` va
doi 2. Nhung `server/worker.py` co:

    if tham_so.check:
        sys.exit(kiem_tra())        # <-- thoat TRUOC khi doc --require-env
    sys.exit(chay(tham_so.require_env))

`--check` la healthcheck doc TEP NHIP: khong mo cong, khong goi mang, va CO Y
khong nap cau hinh moi truong. Nen `--require-env` khong he nam tren duong do.
Bai kiem cu do mot duong khong co rao chan, roi bao rao chan hong.

Rao chan THAT nam trong `chay()` va tra 2 khi FAS_ENV lech
(`server/worker.py`, `return 2`).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
WORKER = GOC / "server" / "worker.py"
NGHIEM_THU = GOC / "scripts" / "ops" / "worker_staging_acceptance.py"


class TestRaoChanMoiTruong(unittest.TestCase):

    def setUp(self):
        self.worker = WORKER.read_text(encoding="utf-8")
        self.nt = NGHIEM_THU.read_text(encoding="utf-8")

    def test_check_short_circuit_truoc_require_env(self):
        """Ghi lai HOP DONG: `--check` thoat truoc, khong doc --require-env."""
        self.assertRegex(
            self.worker,
            r"if tham_so\.check:\s*\n\s*sys\.exit\(kiem_tra\(\)\)",
            "`--check` phai short-circuit — day la hop dong cua healthcheck")
        # Va `--require-env` chi duoc dung o duong `chay()`.
        self.assertIn("sys.exit(chay(tham_so.require_env))", self.worker)

    def test_rao_chan_that_tra_ve_2(self):
        self.assertIn("return 2", self.worker,
                      "lech FAS_ENV phai tra ma 2")

    def test_nghiem_thu_KHONG_dung_check_cho_bai_require_env(self):
        """Bai kiem rao chan KHONG duoc kem `--check` — do sai duong."""
        # Tim doi so cua lan goi server.worker co '--require-env'.
        for m in re.finditer(r"\[sys\.executable,\s*\"-m\",\s*\"server\.worker\"([^\]]*)\]",
                             self.nt, re.S):
            doi = m.group(1)
            if "--require-env" in doi:
                self.assertNotIn(
                    "--check", doi,
                    "bai kiem `--require-env` khong duoc kem `--check`: "
                    "`--check` short-circuit truoc rao chan")

    def test_nghiem_thu_van_doi_ma_2(self):
        self.assertIn("p.returncode == 2", self.nt,
                      "phai van doi dung ma 2 — khong duoc noi long")


if __name__ == "__main__":
    unittest.main()
