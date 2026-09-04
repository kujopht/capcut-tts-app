"""Chan lai hai loi THAT da xay ra khi dung may AWS staging (2026-09-04).

LOI 1 — bao cao "da tao tep env" ma khong he kiem tren may dich.
  `worker_bootstrap.sh` in "da viet mau ..." ngay sau `cat >`, khong kiem lai.
  Bao cao vi vay co the noi tep da co trong khi no khong co, va nguoi doc
  khong co cach nao biet.

LOI 2 — lenh chuyen credential sua may DICH truoc khi biet NGUON co hop le.
  Lenh cu dung `chmod 640 /etc/fanfic-audio/*.env`: dau `*` do SHELL
  KHONG-DAC-QUYEN tren may dich khai trien TRUOC khi `sudo` chay. User
  `ubuntu` khong doc duoc thu muc 0750 root:fanfic nen glob khong no ra, va
  chmod nhan dung chuoi `*.env`:
      chmod: cannot access '/etc/fanfic-audio/*.env': No such file or directory
  Truoc do `sed`/`tee`/`cp` DA chay va DA sua tep dich, du nguon (ben GCE) da
  that bai tu dau vi sai duong dan.

Bo test nay chay `scripts/ops/apply_staging_env.sh` THAT trong mot thu muc
tam, nen no kiem hanh vi chu khong kiem van ban.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
APPLY = GOC / "scripts" / "ops" / "apply_staging_env.sh"
BOOTSTRAP = GOC / "scripts" / "ops" / "worker_bootstrap.sh"

MAU_ENV = """# mau
FAS_ENV=staging
FAS_INLINE_WORKER=false
DATA_BACKEND=appwrite
STORAGE_BACKEND=local
APPWRITE_ENDPOINT=
APPWRITE_PROJECT_ID=
APPWRITE_DATABASE_ID=
APPWRITE_API_KEY=
"""

DU_BON_BIEN = (
    "APPWRITE_ENDPOINT=https://vi-du.test/v1\n"
    "APPWRITE_PROJECT_ID=duan-gia\n"
    "APPWRITE_DATABASE_ID=db-gia\n"
    "APPWRITE_API_KEY=gia-tri-gia-lap-khong-phai-khoa-that\n"
)


def co_bash() -> bool:
    return shutil.which("bash") is not None


@unittest.skipUnless(co_bash(), "can bash")
class TestApplyStagingEnv(unittest.TestCase):
    """`apply_staging_env.sh`: KIEM TRUOC, SUA SAU, ROI KIEM LAI."""

    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.dich = Path(self.d.name) / "etc"
        self.dich.mkdir()
        for f in ("worker.env", "translation-worker.env"):
            (self.dich / f).write_text(MAU_ENV, encoding="utf-8")
        self.addCleanup(self.d.cleanup)

    def chay(self, stdin: str):
        return subprocess.run(
            ["bash", str(APPLY)], input=stdin, capture_output=True, text=True,
            timeout=120,
            env={**os.environ, "DICH_DIR": str(self.dich),
                 "NHOM": "", "PATH": os.environ.get("PATH", "")})

    def noi_dung(self, ten: str) -> str:
        return (self.dich / ten).read_text(encoding="utf-8")

    # -- LOI 2: nguon hong thi KHONG duoc sua tep dich ----------------------
    def test_nguon_RONG_thi_khong_sua_gi(self):
        """Day dung kich ban that: `grep` ben GCE that bai -> stdin rong."""
        truoc = {f: self.noi_dung(f) for f in ("worker.env", "translation-worker.env")}
        kq = self.chay("")
        self.assertNotEqual(kq.returncode, 0, "phai that bai")
        self.assertIn("FAIL", kq.stdout + kq.stderr)
        for f, cu in truoc.items():
            self.assertEqual(self.noi_dung(f), cu,
                             f"{f} BI SUA du nguon rong — dung loi cu")

    def test_nguon_THIEU_MOT_bien_thi_khong_sua_gi(self):
        thieu = DU_BON_BIEN.replace(
            "APPWRITE_API_KEY=gia-tri-gia-lap-khong-phai-khoa-that\n", "")
        truoc = self.noi_dung("worker.env")
        kq = self.chay(thieu)
        self.assertNotEqual(kq.returncode, 0)
        self.assertIn("APPWRITE_API_KEY", kq.stdout + kq.stderr)
        self.assertEqual(self.noi_dung("worker.env"), truoc, "khong duoc sua")

    def test_bien_co_ten_nhung_RONG_gia_tri_khong_duoc_tinh(self):
        rong = DU_BON_BIEN.replace(
            "APPWRITE_API_KEY=gia-tri-gia-lap-khong-phai-khoa-that",
            "APPWRITE_API_KEY=")
        truoc = self.noi_dung("worker.env")
        kq = self.chay(rong)
        self.assertNotEqual(kq.returncode, 0, "dong rong khong duoc tinh la co")
        self.assertEqual(self.noi_dung("worker.env"), truoc)

    def test_nguon_lan_dong_khac_bi_tu_choi(self):
        """Chi nhan dung bon dong Appwrite — khong nuot thu gi khac vao."""
        ban = DU_BON_BIEN + "R2_SECRET_ACCESS_KEY=khong-duoc-phep\n"
        truoc = self.noi_dung("worker.env")
        kq = self.chay(ban)
        self.assertNotEqual(kq.returncode, 0)
        self.assertEqual(self.noi_dung("worker.env"), truoc)

    def test_thieu_tep_dich_thi_bao_ro_va_khong_tao_moi(self):
        (self.dich / "translation-worker.env").unlink()
        kq = self.chay(DU_BON_BIEN)
        self.assertNotEqual(kq.returncode, 0)
        self.assertIn("translation-worker.env", kq.stdout + kq.stderr)
        self.assertFalse((self.dich / "translation-worker.env").exists(),
                         "khong duoc tu tao tep dich")

    # -- duong THANH CONG ---------------------------------------------------
    def test_du_bon_bien_thi_nap_vao_ca_hai_tep(self):
        kq = self.chay(DU_BON_BIEN)
        self.assertEqual(kq.returncode, 0, kq.stdout + kq.stderr)
        self.assertIn("PASS", kq.stdout)
        for f in ("worker.env", "translation-worker.env"):
            n = self.noi_dung(f)
            for v in ("APPWRITE_ENDPOINT", "APPWRITE_PROJECT_ID",
                      "APPWRITE_DATABASE_ID", "APPWRITE_API_KEY"):
                self.assertRegex(n, rf"(?m)^{v}=..*",
                                 f"{v} phai co GIA TRI trong {f}")
            # Dong mau rong phai bi thay, khong duoc con lai ca hai.
            self.assertEqual(n.count("APPWRITE_ENDPOINT="), 1,
                             "khong duoc de lai dong mau rong")
            # Cac bien khac phai con nguyen.
            self.assertIn("FAS_ENV=staging", n)
            self.assertIn("STORAGE_BACKEND=local", n)

    def test_chay_lai_hai_lan_khong_nhan_doi_dong(self):
        self.assertEqual(self.chay(DU_BON_BIEN).returncode, 0)
        self.assertEqual(self.chay(DU_BON_BIEN).returncode, 0)
        n = self.noi_dung("worker.env")
        self.assertEqual(n.count("APPWRITE_API_KEY="), 1, "idempotent")

    def test_KHONG_BAO_GIO_in_gia_tri_bi_mat(self):
        """Bai quan trong nhat ve bao mat: dau ra chi duoc co TEN bien."""
        kq = self.chay(DU_BON_BIEN)
        ra = kq.stdout + kq.stderr
        self.assertNotIn("gia-tri-gia-lap-khong-phai-khoa-that", ra)
        self.assertNotIn("duan-gia", ra)
        self.assertNotIn("db-gia", ra)


@unittest.skipUnless(co_bash(), "can bash")
class TestBootstrapKiemLaiEnv(unittest.TestCase):
    """LOI 1: bootstrap khong duoc BAO da tao tep ma khong kiem lai."""

    def test_bootstrap_kiem_lai_sau_khi_viet_mau(self):
        src = BOOTSTRAP.read_text(encoding="utf-8")
        # Phai co mot buoc doc lai/kiem su ton tai sau khi ghi mau, khong
        # duoc chi `cat >` roi `echo "da viet"`.
        self.assertRegex(
            src, r'\[ -f "\$mau" \]|\[ -s "\$mau" \]|test -f "\$mau"',
            "worker_bootstrap.sh phai KIEM LAI tep mau that su ton tai "
            "truoc khi bao da tao")

    def test_bootstrap_khong_dung_glob_trong_duong_dac_quyen(self):
        """Glob trong thu muc 0750 no ra o shell khong-dac-quyen -> hong."""
        src = BOOTSTRAP.read_text(encoding="utf-8")
        # Khong dua ca tep vao thong bao loi: no dai hang tram dong va lam
        # ket qua test khong doc duoc. Chi ra dong vi pham.
        xau = [f"dong {i}: {l.strip()[:90]}"
               for i, l in enumerate(src.splitlines(), 1)
               if "/etc/fanfic-audio/*.env" in l]
        self.assertEqual(xau, [], "khong duoc dung glob tren thu muc 0750: "
                                  + "; ".join(xau))


if __name__ == "__main__":
    unittest.main()
