"""`apply_staging_r2.sh` — rao chan BUCKET dat o BIEN GIOI CHUYEN GIAO.

Yeu cau cot loi cua chan R2: staging KHONG BAO GIO duoc ghi vao kho
production. Cach chac chan nhat la chan ngay khi credential di qua bien —
truoc khi mot byte nao duoc ghi vao tep env — chu khong phai chi kiem luc
worker khoi dong.

Rao chan la ALLOWLIST: "khong phai fanfic-prod nen coi la an toan" la sai,
vi mot bucket production KHAC hoac mot lan go sai ten van phai bi tu choi.

Bo test chay script THAT tren thu muc tam nen no kiem hanh vi.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
APPLY = GOC / "scripts" / "ops" / "apply_staging_r2.sh"
NGHIEM_THU = GOC / "scripts" / "ops" / "worker_staging_acceptance.py"

MAU_ENV = """FAS_ENV=staging
FAS_INLINE_WORKER=false
DATA_BACKEND=appwrite
STORAGE_BACKEND=local
FAS_LOCAL_VOICES=piper:ngochuyen
APPWRITE_ENDPOINT=https://vi-du.test/v1
APPWRITE_PROJECT_ID=duan-gia
APPWRITE_DATABASE_ID=db-gia
APPWRITE_API_KEY=khoa-gia-lap
R2_ACCOUNT_ID=
R2_BUCKET=
"""


def bo_r2(bucket: str) -> str:
    return (
        "R2_ACCOUNT_ID=taikhoan-gia-lap\n"
        "R2_ACCESS_KEY_ID=khoa-truy-cap-gia-lap\n"
        "R2_SECRET_ACCESS_KEY=khoa-bi-mat-gia-lap\n"
        f"R2_BUCKET={bucket}\n"
    )


def co_bash() -> bool:
    return shutil.which("bash") is not None


@unittest.skipUnless(co_bash(), "can bash")
class TestChuyenGiaoR2(unittest.TestCase):

    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.dir = Path(self.d.name)
        self.addCleanup(self.d.cleanup)
        for f in ("worker.env", "translation-worker.env"):
            (self.dir / f).write_text(MAU_ENV, encoding="utf-8")

    def chay(self, stdin: str):
        return subprocess.run(
            ["bash", str(APPLY)], input=stdin, capture_output=True, text=True,
            timeout=120,
            env={**os.environ, "DICH_DIR": str(self.dir), "NHOM": "",
                 "PATH": os.environ.get("PATH", "")})

    def doc(self, ten: str, khoa: str) -> str:
        gt = ""
        for d in (self.dir / ten).read_text(encoding="utf-8").splitlines():
            if d.startswith(f"{khoa}="):
                gt = d.split("=", 1)[1]
        return gt

    # -- RAO CHAN BUCKET ----------------------------------------------------
    def test_bucket_PRODUCTION_bi_tu_choi_va_khong_sua_gi(self):
        truoc = (self.dir / "worker.env").read_text(encoding="utf-8")
        kq = self.chay(bo_r2("fanfic-prod"))
        self.assertNotEqual(kq.returncode, 0)
        self.assertIn("PRODUCTION", kq.stdout + kq.stderr)
        self.assertEqual((self.dir / "worker.env").read_text(encoding="utf-8"),
                         truoc, "KHONG duoc sua tep khi bucket la production")

    def test_bucket_LA_bi_tu_choi_fail_closed(self):
        """Allowlist: mot ten khong biet bi tu choi, ke ca khi khac prod."""
        for b in ("fanfic-prod-2", "fanfic-production", "my-bucket",
                  "fanfic-prod-backup", ""):
            truoc = (self.dir / "worker.env").read_text(encoding="utf-8")
            kq = self.chay(bo_r2(b))
            self.assertNotEqual(kq.returncode, 0, f"{b!r} phai bi tu choi")
            self.assertEqual((self.dir / "worker.env").read_text(encoding="utf-8"),
                             truoc, f"{b!r}: khong duoc sua tep")

    def test_bucket_STAGING_duoc_nhan(self):
        kq = self.chay(bo_r2("fanfic-staging"))
        self.assertEqual(kq.returncode, 0, kq.stdout + kq.stderr)
        self.assertIn("PASS", kq.stdout)
        for f in ("worker.env", "translation-worker.env"):
            self.assertEqual(self.doc(f, "R2_BUCKET"), "fanfic-staging")
            for v in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID",
                      "R2_SECRET_ACCESS_KEY"):
                self.assertNotEqual(self.doc(f, v), "", f"{v} phai co gia tri")

    # -- KIEM TRUOC, SUA SAU ------------------------------------------------
    def test_nguon_rong_khong_sua_gi(self):
        truoc = (self.dir / "worker.env").read_text(encoding="utf-8")
        self.assertNotEqual(self.chay("").returncode, 0)
        self.assertEqual((self.dir / "worker.env").read_text(encoding="utf-8"), truoc)

    def test_nguon_thieu_mot_bien_khong_sua_gi(self):
        thieu = bo_r2("fanfic-staging").replace(
            "R2_SECRET_ACCESS_KEY=khoa-bi-mat-gia-lap\n", "")
        truoc = (self.dir / "worker.env").read_text(encoding="utf-8")
        kq = self.chay(thieu)
        self.assertNotEqual(kq.returncode, 0)
        self.assertIn("R2_SECRET_ACCESS_KEY", kq.stdout + kq.stderr)
        self.assertEqual((self.dir / "worker.env").read_text(encoding="utf-8"), truoc)

    def test_nguon_lan_dong_khac_bi_tu_choi(self):
        ban = bo_r2("fanfic-staging") + "APPWRITE_API_KEY=khong-duoc-phep\n"
        truoc = (self.dir / "worker.env").read_text(encoding="utf-8")
        self.assertNotEqual(self.chay(ban).returncode, 0)
        self.assertEqual((self.dir / "worker.env").read_text(encoding="utf-8"), truoc)

    # -- giu nguyen phan con lai --------------------------------------------
    def test_khong_lam_mat_bien_khac(self):
        self.assertEqual(self.chay(bo_r2("fanfic-staging")).returncode, 0)
        for f in ("worker.env", "translation-worker.env"):
            noi = (self.dir / f).read_text(encoding="utf-8")
            for k in ("FAS_ENV=staging", "DATA_BACKEND=appwrite",
                      "FAS_LOCAL_VOICES=piper:ngochuyen"):
                self.assertIn(k, noi, f"{f} mat {k}")
            self.assertNotEqual(self.doc(f, "APPWRITE_API_KEY"), "",
                                "khong duoc lam mat bi mat Appwrite")

    def test_idempotent(self):
        self.assertEqual(self.chay(bo_r2("fanfic-staging")).returncode, 0)
        n1 = (self.dir / "worker.env").read_text(encoding="utf-8")
        self.assertEqual(self.chay(bo_r2("fanfic-staging")).returncode, 0)
        n2 = (self.dir / "worker.env").read_text(encoding="utf-8")
        self.assertEqual(n1, n2)
        self.assertEqual(n2.count("R2_BUCKET="), 1, "khong duoc nhan doi dong")

    def test_KHONG_in_gia_tri_bi_mat(self):
        kq = self.chay(bo_r2("fanfic-staging"))
        ra = kq.stdout + kq.stderr
        for x in ("khoa-bi-mat-gia-lap", "khoa-truy-cap-gia-lap",
                  "taikhoan-gia-lap"):
            self.assertNotIn(x, ra, "khong duoc in gia tri bi mat")
        # Ten bucket KHONG phai bi mat va CAN doc duoc.
        self.assertIn("fanfic-staging", ra)

    def test_chuan_hoa_CRLF(self):
        crlf = MAU_ENV.replace("\n", "\r\n").encode("utf-8")
        for f in ("worker.env", "translation-worker.env"):
            (self.dir / f).write_bytes(crlf)
        self.assertEqual(self.chay(bo_r2("fanfic-staging")).returncode, 0)
        for f in ("worker.env", "translation-worker.env"):
            self.assertNotIn(b"\r", (self.dir / f).read_bytes())


class TestHaiNoiCungMotDanhSach(unittest.TestCase):
    """Danh sach bucket staging phai khop giua script chuyen giao va bo
    nghiem thu — hai cho lech nhau la mot lo hong im lang."""

    def test_danh_sach_bucket_khop_nhau(self):
        sh = APPLY.read_text(encoding="utf-8")
        py = NGHIEM_THU.read_text(encoding="utf-8")
        for b in ("fanfic-staging", "fanfic-dev"):
            self.assertIn(b, sh, f"{b} phai co trong apply_staging_r2.sh")
            self.assertIn(b, py, f"{b} phai co trong worker_staging_acceptance.py")
        self.assertIn("fanfic-prod", sh, "phai chan tuong minh ten production")


if __name__ == "__main__":
    unittest.main()
