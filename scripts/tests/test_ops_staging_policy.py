"""Chan lai su co THAT tren may AWS staging (2026-09-04).

    ConfigError: STORAGE_BACKEND=r2 nhung thieu cau hinh. Can du bon bien:
    R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
        server/main.py:229 -> server/config.py:618

Quan sat ban dau la "fanfic-worker active, translation failed", de nghi
huong hai tep env lech nhau. Doc log thi KHONG PHAI: CA HAI tep deu
`STORAGE_BACKEND=r2` va ca hai worker chet voi CUNG mot ConfigError; lan
"active" kia la cua so giua hai lan `Restart=always` truoc khi cham
`StartLimitBurst=5`.

Goc re: `worker_bootstrap.sh` co quy tac "khong ghi de tep env da ton tai".
Quy tac do DUNG cho bi mat, nhung no da bi ap cho CA TEP — ke ca cac khoa
CHINH SACH khong-bi-mat. Hai tep sinh tu ban mau CU (khi mau con
`STORAGE_BACKEND=r2`) giu gia tri do mai mai; ban mau sau do doi sang
`local` nhung thay doi khong bao gio toi duoc may.

Bo test giu CA HAI kich ban: hai tep cung sai (thuc te da xay ra) VA hai
tep lech nhau (chua xay ra nhung hoan toan co the, va cung mot co che sinh
ra no).

Bo test nay chay `staging_reconcile_env.sh` THAT tren thu muc tam, nen no
kiem hanh vi chu khong kiem van ban.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
RECONCILE = GOC / "scripts" / "ops" / "staging_reconcile_env.sh"
BOOTSTRAP = GOC / "scripts" / "ops" / "worker_bootstrap.sh"

KHOA_CHINH_SACH = ("FAS_ENV", "DATA_BACKEND", "STORAGE_BACKEND",
                   "FAS_INLINE_WORKER", "FAS_LOCAL_VOICES")
BI_MAT = ("APPWRITE_ENDPOINT", "APPWRITE_PROJECT_ID",
          "APPWRITE_DATABASE_ID", "APPWRITE_API_KEY")

#: Ban mau CU — dung hai loi da gay ra su co that:
#:   STORAGE_BACKEND=r2   -> ConfigError, worker khong khoi dong duoc
#:   FAS_LOCAL_VOICES=    -> `local_voices: []`, worker NHAN job roi that bai
#:                           voi VOICE_NOT_FOUND (vi model CO tren dia nen
#:                           cong vat ly cho qua, con cong san pham thi khong)
CU_R2 = """FAS_ENV=staging
FAS_INLINE_WORKER=false
DATA_BACKEND=appwrite
STORAGE_BACKEND=r2
FAS_LOCAL_VOICES=
APPWRITE_ENDPOINT=https://vi-du.test/v1
APPWRITE_PROJECT_ID=duan-gia
APPWRITE_DATABASE_ID=db-gia
APPWRITE_API_KEY=gia-tri-gia-lap
R2_ACCOUNT_ID=
R2_BUCKET=
"""

MOI_LOCAL = (CU_R2.replace("STORAGE_BACKEND=r2", "STORAGE_BACKEND=local")
                  .replace("FAS_LOCAL_VOICES=\n",
                           "FAS_LOCAL_VOICES=piper:ngochuyen\n"))


def co_bash() -> bool:
    return shutil.which("bash") is not None


@unittest.skipUnless(co_bash(), "can bash")
class TestChinhSachStagingDongNhat(unittest.TestCase):

    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.dir = Path(self.d.name)
        self.addCleanup(self.d.cleanup)

    def viet(self, worker: str, translation: str) -> None:
        (self.dir / "worker.env").write_text(worker, encoding="utf-8")
        (self.dir / "translation-worker.env").write_text(translation,
                                                         encoding="utf-8")

    def chay(self, *args: str):
        return subprocess.run(
            ["bash", str(RECONCILE), *args], capture_output=True, text=True,
            timeout=120,
            env={**os.environ, "DICH_DIR": str(self.dir), "NHOM": "",
                 "PATH": os.environ.get("PATH", "")})

    def gia_tri(self, ten: str, khoa: str) -> str:
        for d in (self.dir / ten).read_text(encoding="utf-8").splitlines():
            if d.startswith(f"{khoa}="):
                v = d.split("=", 1)[1]
        return locals().get("v", "")

    def doc_cuoi(self, ten: str, khoa: str) -> str:
        gt = ""
        for d in (self.dir / ten).read_text(encoding="utf-8").splitlines():
            if d.startswith(f"{khoa}="):
                gt = d.split("=", 1)[1]
        return gt

    # -- TAI HIEN DUNG SU CO -------------------------------------------------
    def test_tai_hien_su_co_hai_tep_lech_nhau(self):
        """worker=local nhung translation=r2 — dung hinh dang da xay ra."""
        self.viet(MOI_LOCAL, CU_R2)
        kq = self.chay("--print-only")
        self.assertNotEqual(kq.returncode, 0, "phai phat hien duoc su lech")
        self.assertIn("LECH", kq.stdout)
        self.assertIn("STORAGE_BACKEND", kq.stdout)

    def test_dong_bo_lam_hai_tep_GIONG_NHAU(self):
        self.viet(MOI_LOCAL, CU_R2)
        kq = self.chay()
        self.assertEqual(kq.returncode, 0, kq.stdout + kq.stderr)
        for khoa in KHOA_CHINH_SACH:
            a = self.doc_cuoi("worker.env", khoa)
            b = self.doc_cuoi("translation-worker.env", khoa)
            self.assertEqual(a, b, f"{khoa} van lech sau khi dong bo")

    def test_storage_backend_ve_local_tren_MOI_tep(self):
        """Yeu cau cot loi: staging local-storage cho TAT CA worker."""
        self.viet(CU_R2, CU_R2)
        self.assertEqual(self.chay().returncode, 0)
        for f in ("worker.env", "translation-worker.env"):
            self.assertEqual(self.doc_cuoi(f, "STORAGE_BACKEND"), "local",
                             f"{f} phai la local")
            self.assertEqual(self.doc_cuoi(f, "FAS_ENV"), "staging")
            self.assertEqual(self.doc_cuoi(f, "DATA_BACKEND"), "appwrite")
            self.assertEqual(self.doc_cuoi(f, "FAS_INLINE_WORKER"), "false")

    def test_KHONG_them_bien_R2_nao(self):
        """Sua bang cach doi chinh sach, TUYET DOI khong tiem credential R2."""
        self.viet(CU_R2, CU_R2)
        self.assertEqual(self.chay().returncode, 0)
        for f in ("worker.env", "translation-worker.env"):
            noi = (self.dir / f).read_text(encoding="utf-8")
            for k in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
                for dong in noi.splitlines():
                    if dong.startswith(f"{k}="):
                        self.assertEqual(
                            dong.split("=", 1)[1], "",
                            f"{k} phai van RONG — khong duoc tiem credential")

    def test_BI_MAT_con_nguyen_sau_khi_dong_bo(self):
        self.viet(CU_R2, CU_R2)
        self.assertEqual(self.chay().returncode, 0)
        for f in ("worker.env", "translation-worker.env"):
            for k in BI_MAT:
                self.assertNotEqual(self.doc_cuoi(f, k), "",
                                    f"{k} bi mat sau khi dong bo {f}")

    def test_khong_in_gia_tri_bi_mat(self):
        self.viet(CU_R2, CU_R2)
        kq = self.chay()
        self.assertNotIn("gia-tri-gia-lap", kq.stdout + kq.stderr)
        self.assertNotIn("duan-gia", kq.stdout + kq.stderr)

    def test_idempotent(self):
        self.viet(CU_R2, CU_R2)
        self.assertEqual(self.chay().returncode, 0)
        n1 = (self.dir / "worker.env").read_text(encoding="utf-8")
        self.assertEqual(self.chay().returncode, 0)
        n2 = (self.dir / "worker.env").read_text(encoding="utf-8")
        self.assertEqual(n1, n2, "chay lai khong duoc lam doi noi dung")
        self.assertEqual(n2.count("STORAGE_BACKEND="), 1,
                         "khong duoc nhan doi dong chinh sach")

    def test_print_only_KHONG_sua_gi(self):
        self.viet(CU_R2, CU_R2)
        truoc = (self.dir / "worker.env").read_text(encoding="utf-8")
        self.chay("--print-only")
        self.assertEqual((self.dir / "worker.env").read_text(encoding="utf-8"),
                         truoc)

    def test_da_dung_roi_thi_bao_khong_lech(self):
        self.viet(MOI_LOCAL, MOI_LOCAL)
        kq = self.chay("--print-only")
        self.assertEqual(kq.returncode, 0, kq.stdout)
        self.assertIn("khong lech", kq.stdout)

    # -- SU CO GIONG: FAS_LOCAL_VOICES rong -> tat HET giong cuc bo ----------
    def test_FAS_LOCAL_VOICES_rong_bi_phat_hien_va_sua(self):
        """De TRONG khac han voi KHONG DAT (server/config.py:719).

        Ban mau cu ghi `FAS_LOCAL_VOICES=` nen worker chay voi
        `local_voices: []` va tu choi MOI giong Piper. Vi model CO tren dia,
        worker NHAN job (cong vat ly cho qua) roi that bai voi
        VOICE_NOT_FOUND — job chet chu khong duoc nhuong.
        """
        self.viet(CU_R2, CU_R2)
        kq = self.chay("--print-only")
        self.assertNotEqual(kq.returncode, 0, "phai phat hien FAS_LOCAL_VOICES rong")
        self.assertIn("FAS_LOCAL_VOICES", kq.stdout)

        self.assertEqual(self.chay().returncode, 0)
        for f in ("worker.env", "translation-worker.env"):
            self.assertEqual(self.doc_cuoi(f, "FAS_LOCAL_VOICES"),
                             "piper:ngochuyen",
                             f"{f}: phai dat tuong minh bang mac dinh ma nguon")

    def test_khong_noi_rong_pham_vi_giong(self):
        """Sua bang cach dat DUNG mac dinh cua ma nguon, khong them giong moi.

        `server/config.py:431` -> Settings.local_voices = ("piper:ngochuyen",).
        Neu mot ngay ai do them giong vao day, bai nay bat phai co y.
        """
        self.viet(CU_R2, CU_R2)
        self.assertEqual(self.chay().returncode, 0)
        gt = self.doc_cuoi("worker.env", "FAS_LOCAL_VOICES")
        self.assertEqual(gt, "piper:ngochuyen",
                         "khong duoc chao ban them giong nao ngoai mac dinh")
        self.assertNotIn("ngochuyennew", gt,
                         "`ngochuyennew` KHONG nam trong mac dinh san pham")


@unittest.skipUnless(co_bash(), "can bash")
class TestBootstrapDongBoChinhSach(unittest.TestCase):
    """Bootstrap PHAI dong bo chinh sach ke ca khi tep env da ton tai."""

    def test_bootstrap_goi_reconcile(self):
        src = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn("staging_reconcile_env.sh", src,
                      "bootstrap phai dong bo chinh sach, khong duoc de mot "
                      "tep env cu giu gia tri lac hau mai mai")

    def test_bootstrap_van_khong_ghi_de_tep_da_co(self):
        """Bi mat van phai duoc bao ve — khong duoc 'sua' bang cach ghi de."""
        src = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn('giu nguyen $mau (da co)', src)


if __name__ == "__main__":
    unittest.main()
