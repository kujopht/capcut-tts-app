"""Cong dieu hanh HEP cho AWS staging — kiem ALLOWLIST va GIOI HAN DUONG DAN.

Day la ma chay bang ROOT, nen no la be mat tan cong. Bo test nay ton tai de
mot lan sua vo y khong bien no thanh duong leo thang quyen tuy y.

Bat bien phai giu:
  1. CHI sau verb duoc phep; moi thu khac TU CHOI (fail closed)
  2. verb KHONG BAO GIO di vao shell — khong `eval`, khong noi chuoi
  3. khong nhan tham so duong dan tu ben ngoai
  4. TU CHOI moi unit mang chu "prod"
  5. co audit
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
ADMIN = GOC / "scripts" / "ops" / "fanfic_staging_admin.sh"
INSTALL = GOC / "scripts" / "ops" / "install_staging_admin.sh"

VERB_DUOC_PHEP = {"status", "reconcile", "reconcile-r2", "restart", "logs",
                  "run-proof", "update"}


def co_bash() -> bool:
    return shutil.which("bash") is not None


class TestAllowlist(unittest.TestCase):
    """Doc TRUC TIEP ma nguon: allowlist phai dong cung, khong sinh dong."""

    def setUp(self):
        self.src = ADMIN.read_text(encoding="utf-8")

    def test_allowlist_dong_cung_va_dung_bo_verb(self):
        m = re.search(r'^ALLOW="([^"]+)"', self.src, re.M)
        self.assertIsNotNone(m, "phai co bien ALLOW dong cung")
        self.assertEqual(set(m.group(1).split()), VERB_DUOC_PHEP)

    def test_khong_co_eval_hay_shell_tuy_y(self):
        xau = []
        for i, l in enumerate(self.src.splitlines(), 1):
            t = l.strip()
            if t.startswith("#"):
                continue
            for mau in ("eval ", "eval\t", "bash -c", "sh -c", "$(<"):
                if mau in t:
                    xau.append(f"dong {i}: {mau}")
        self.assertEqual(xau, [], f"khong duoc co shell tuy y: {xau}")

    def test_verb_khong_duoc_noi_vao_lenh(self):
        """`case "$v" in` la cach dung; `$verb` trong mot lenh thi khong."""
        self.assertIn('case "$v" in', self.src,
                      "phai dispatch bang `case`, khong noi chuoi")
        # `$verb` chi duoc xuat hien khi GAN hoac khi truyen cho chay_verb,
        # khong duoc nam trong mot lenh khac.
        for i, l in enumerate(self.src.splitlines(), 1):
            t = l.strip()
            if "$verb" in t and not t.startswith("#"):
                self.assertTrue(
                    t.startswith("verb=") or "chay_verb \"$verb\"" in t
                    or 'echo "# verb=$verb' in t,
                    f"dong {i} dung $verb khong an toan: {t}")

    def test_loc_ky_tu_cua_verb(self):
        """Verb doc tu tep phai bi loc con [a-z0-9-], chan moi ky tu shell.

        Chu SO can co: `reconcile-r2` la verb hop le. Loc cu (`a-z-`) cat mat
        so 2, bien no thanh `reconcile-r` roi bi allowlist tu choi mot cach
        kho hieu.
        """
        self.assertIn("tr -cd 'a-z0-9-'", self.src,
                      "phai loc verb con chu thuong, chu so va dau gach")

    def test_reconcile_r2_fail_closed(self):
        """`reconcile-r2` phai TU CHOI khi chua du dieu kien."""
        self.assertIn("vh_reconcile_r2", self.src)
        # Phai kiem bon bien R2 va allowlist bucket TRUOC khi doi chinh sach.
        for k in ("R2_ACCOUNT_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
            self.assertIn(k, self.src, f"phai kiem {k}")
        self.assertIn("fanfic-prod", self.src,
                      "phai chan tuong minh bucket production")
        self.assertIn("BUCKET_STAGING", self.src, "phai co allowlist bucket")

    def test_hai_verb_rieng_cho_hai_chinh_sach_luu_tru(self):
        """`reconcile` va `reconcile-r2` la HAI verb, khong phai mot verb
        nhan tham so — de lua chon kho luu tru la tuong minh trong allowlist
        va trong audit log."""
        self.assertIn("reconcile) vh_reconcile ;;", self.src)
        self.assertIn("reconcile-r2) vh_reconcile_r2 ;;", self.src)

    def test_chan_unit_production(self):
        self.assertIn("*prod*", self.src, "phai TU CHOI unit mang chu prod")
        self.assertIn("kiem_unit", self.src)

    def test_danh_sach_unit_dong_cung(self):
        m = re.search(r"^UNITS=\(([^)]+)\)", self.src, re.M)
        self.assertIsNotNone(m)
        units = m.group(1).split()
        self.assertEqual(len(units), 3, f"chi ba unit staging: {units}")
        for u in units:
            self.assertNotIn("prod", u, f"{u} mang chu prod")

    def test_co_audit(self):
        self.assertIn("ghi_audit", self.src)
        self.assertIn("/var/log/fanfic-staging-admin.log", self.src)

    def test_khong_nhan_tham_so_duong_dan(self):
        """Khong duoc co bien duong dan nao lay tu $2/$3."""
        for i, l in enumerate(self.src.splitlines(), 1):
            t = l.strip()
            if t.startswith("#"):
                continue
            self.assertNotRegex(t, r'\$\{?[23]\}?',
                                f"dong {i} nhan tham so thu 2/3: {t}")

    def test_khong_cai_sudoers_hay_setuid(self):
        """Quet dong MA, khong quet ghi chu.

        Ca hai tep CO Y nhac ten `NOPASSWD` trong ghi chu de noi ro rang
        chung khong dung no. Quet ca ghi chu thi bai test se cam viec giai
        thich — sai doi tuong.
        """
        for f in (ADMIN, INSTALL):
            xau = []
            for i, l in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                t = l.strip()
                if not t or t.startswith("#"):
                    continue
                for m in ("NOPASSWD", "/etc/sudoers", "chmod u+s", "chmod 4755"):
                    if m in t:
                        xau.append(f"{f.name}:{i} {m}")
            self.assertEqual(xau, [], f"dong ma vi pham: {xau}")


@unittest.skipUnless(co_bash(), "can bash")
class TestHanhViThat(unittest.TestCase):
    """Chay script THAT: verb ngoai allowlist phai bi tu choi."""

    def chay(self, verb: str):
        return subprocess.run(
            ["bash", str(ADMIN), verb], capture_output=True, text=True,
            timeout=60, env={**os.environ, "PATH": os.environ.get("PATH", "")})

    def test_verb_la_bi_tu_choi_fail_closed(self):
        for v in ("rm", "bash", "sudo", "deploy", "publish", "cutover",
                  "status; rm -rf /", "../../etc/passwd", "prod-restart"):
            kq = self.chay(v)
            self.assertNotEqual(kq.returncode, 0, f"{v!r} phai bi tu choi")
            self.assertIn("TU CHOI", kq.stdout + kq.stderr,
                          f"{v!r} phai bao TU CHOI")

    def test_khong_verb_thi_in_huong_dan(self):
        kq = subprocess.run(["bash", str(ADMIN)], capture_output=True,
                            text=True, timeout=60)
        self.assertNotEqual(kq.returncode, 0)
        self.assertIn("dung:", kq.stdout + kq.stderr)

    def test_verb_duoc_phep_KHONG_bi_tu_choi_o_khau_allowlist(self):
        """`status` phai qua duoc allowlist. Tren may khong phai staging no se
        that bai o cac lenh ben trong — dieu do binh thuong; dieu can kiem la
        no KHONG bi chan o khau allowlist."""
        kq = self.chay("status")
        self.assertNotIn("khong nam trong allowlist", kq.stdout + kq.stderr)


class TestRunnerKhongPhuThuocHome(unittest.TestCase):
    """`staging_run_all.sh` chay QUA cong dieu hanh, va unit cua cong do co
    `ProtectHome=true` — /home KHONG nhin thay duoc.

    Su co that (2026-09-04): runner tro vao /home/ubuntu/*.py nen ca hai
    buoc do voi "No such file or directory" -> nghiem thu=2, job=2,
    AWS_STAGING_FAIL. Chinh lop bao ve toi them vao lam vo duong dan.
    """

    def test_runner_khong_tro_vao_home(self):
        p = GOC / "scripts" / "ops" / "staging_run_all.sh"
        xau = []
        for i, l in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            t = l.strip()
            if not t or t.startswith("#"):
                continue
            if "/home/" in t:
                xau.append(f"dong {i}: {t[:80]}")
        self.assertEqual(xau, [], f"ProtectHome=true -> /home khong doc duoc: {xau}")

    def test_unit_van_giu_ProtectHome(self):
        """Sua bang cach doi duong dan, KHONG bang cach bo lop bao ve."""
        s = INSTALL.read_text(encoding="utf-8")
        self.assertIn("ProtectHome=true", s,
                      "khong duoc noi long hardening de lam duong dan chay duoc")

    def test_runner_dat_FAS_VAR_DIR_theo_unit(self):
        """`FAS_VAR_DIR` khong nam trong tep env — no la `Environment=` cua
        unit. Bo qua no thi `settings.var_dir` lui ve `server/var` tuong doi
        voi kho, nen ban chung minh di tim hien vat SAI CHO.

        Da do that: job COMPLETED nhung "ton tai=False" -> exit 7, vi worker
        ghi vao /var/lib/fanfic-audio/storage con ban chung minh doc
        /opt/fanfic-audio/server/var/storage.
        """
        s = (GOC / "scripts" / "ops" / "staging_run_all.sh").read_text(encoding="utf-8")
        self.assertIn("FAS_VAR_DIR", s, "runner phai dat FAS_VAR_DIR")
        self.assertIn("systemctl show fanfic-worker.service -p Environment", s,
                      "phai lay THANG tu unit de khong lech nhau")

    def test_runner_cat_bo_CR_khi_nap_env(self):
        """`.` cua bash khong cat \\r nhu systemd — phai tu lo."""
        s = (GOC / "scripts" / "ops" / "staging_run_all.sh").read_text(encoding="utf-8")
        self.assertIn("tr -d '\\r'", s,
                      "phai cat \\r truoc khi source tep env")

    def test_runner_KHONG_ep_storage_backend_ve_local(self):
        """`run-proof` phai GIU NGUYEN kho luu tru dang duoc cau hinh.

        Su co that (2026-09-04): runner goi reconcile khong kem tham so, nen
        no ap mac dinh `STORAGE_BACKEND=local`. Sau khi `reconcile-r2` da dat
        r2, mot lan `run-proof` LAT NGUOC ve local roi chay nghiem thu + job
        DRAFT o che do local — va bao PASS. Do la PASS GIA cho chan R2: no
        chung minh lai dung cai da chung minh roi.
        """
        s = (GOC / "scripts" / "ops" / "staging_run_all.sh").read_text(encoding="utf-8")
        self.assertIn("STORAGE_BACKEND_MONG_MUON", s,
                      "runner phai truyen kho luu tru hien tai cho reconcile")
        # Va phai DOC gia tri hien tai tu tep env, khong dong cung.
        self.assertRegex(
            s, r"grep -E '\^STORAGE_BACKEND=' \"\$ENVD/worker\.env\"",
            "phai doc STORAGE_BACKEND hien tai tu worker.env")

    def test_runner_dung_script_trong_checkout(self):
        s = (GOC / "scripts" / "ops" / "staging_run_all.sh").read_text(encoding="utf-8")
        for ten in ("worker_staging_acceptance.py", "staging_draft_job_proof.py",
                    "staging_reconcile_env.sh"):
            self.assertIn(f'$APP/scripts/ops/{ten}', s,
                          f"{ten} phai lay tu checkout (ma nguon da merge)")


class TestTrinhCai(unittest.TestCase):

    def test_installer_khong_mo_rong_quyen(self):
        s = INSTALL.read_text(encoding="utf-8")
        self.assertIn("0730", s, "hang doi req phai 0730 (ghi, khong liet ke)")
        self.assertIn("NoNewPrivileges=true", s)
        # Quet dong MA, khong quet ghi chu — xem ly le o
        # TestAllowlist.test_khong_cai_sudoers_hay_setuid.
        xau = []
        for i, l in enumerate(s.splitlines(), 1):
            t = l.strip()
            if not t or t.startswith("#"):
                continue
            for m in ("NOPASSWD", "sudoers", "chmod 777", "chmod a+w"):
                if m in t:
                    xau.append(f"dong {i}: {m}")
        self.assertEqual(xau, [], f"dong ma vi pham: {xau}")

    def test_installer_doi_root(self):
        s = INSTALL.read_text(encoding="utf-8")
        self.assertIn('[ "$(id -u)" -eq 0 ]', s, "phai doi root")


if __name__ == "__main__":
    unittest.main()
