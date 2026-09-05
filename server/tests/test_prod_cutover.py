"""Bai kiem cho cac phep chuyen trang thai NGUY HIEM cua `prod_cutover.py`.

Khong cham may that: `aws()`, `gce()`, `cong()` va bo do hang doi deu bi
thay bang ban gia. Cai duoc kiem o day la LOGIC RAO CHAN, khong phai SSH.

Bon che do that bai duoc nham toi:
  1. AWS va GCE cung chay -> hai worker claim CUNG mot hang doi production
  2. DRAIN dung GCE khi con job dang chay -> giet mot ban tong hop that
  3. CANARY that bai ma khong lui -> production khong con worker nao
  4. COMMIT khi trang thai chua sach -> chot mot cau hinh sai
"""
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ops import prod_cutover as pc  # noqa: E402
from scripts.ops.cutover_target import PROD_UNITS, STAGING_UNITS  # noqa: E402


def ns(**kw):
    m = {"wait": 60, "minutes": 1, "every": 1, "dry_run": False, "allow_both": False}
    m.update(kw)
    return argparse.Namespace(**m)


def units(active_prod=True, active_staging=False):
    """Ban do unit cua may AWS: mang CA production LAN staging."""
    d = {u: ("active" if active_prod else "inactive") for u in PROD_UNITS}
    d.update({u: ("active" if active_staging else "inactive") for u in STAGING_UNITS})
    return d


def units_gce(active=True):
    """Ban do unit cua may GCE: CHI ba unit production. GCE khong co unit
    staging nao — tron hai thu la ly do mot bai kiem tung do sai."""
    return {u: ("active" if active else "inactive") for u in PROD_UNITS}


def ban_do(pending=0, running=0, treo=0):
    return {
        "so_luong": {"pending": pending, "running": running},
        "lease_treo": [{"job_id": f"j{i}"} for i in range(treo)],
        "dang_chay": [],
        "cho_xu_ly": [],
        "an_toan_de_ban_giao": running == 0 and treo == 0,
    }


class ProbeGia:
    """Thay `scripts.ops.prod_probe` — khong mang, khong credential."""

    def __init__(self, bd, dat=True):
        self._bd = bd
        self._dat = dat

    def nap_env_production(self):
        return {}

    def do_hang_doi(self):
        return dict(self._bd)

    def cho_hang_doi_rong(self, han, nhip_giay=15):
        b = dict(self._bd)
        b["dat"] = self._dat
        b["so_lan_do"] = 1
        return b


def _vaProbe(bd, dat=True):
    """Cam ban gia vao `sys.modules` de `from scripts.ops import prod_probe` thay."""
    return mock.patch.dict(sys.modules,
                           {"scripts.ops.prod_probe": ProbeGia(bd, dat)})


class Drain(unittest.TestCase):
    """DRAIN khong bao gio duoc giet mot ban tong hop dang chay."""

    def test_TU_CHOI_dung_GCE_khi_con_job_running(self):
        goi = []
        with _vaProbe(ban_do(running=2), dat=False), \
             mock.patch.object(pc, "gce", side_effect=lambda *a, **k: goi.append(a) or (0, "", "")), \
             mock.patch.object(pc, "ghi_audit"):
            ma = pc.pha_drain(ns())
        self.assertEqual(ma, 2)
        self.assertEqual(goi, [], "KHONG duoc goi GCE khi con job dang chay")

    def test_TU_CHOI_khi_co_lease_treo(self):
        goi = []
        with _vaProbe(ban_do(running=0, treo=1), dat=True), \
             mock.patch.object(pc, "gce", side_effect=lambda *a, **k: goi.append(a) or (0, "", "")), \
             mock.patch.object(pc, "ghi_audit"):
            ma = pc.pha_drain(ns())
        self.assertEqual(ma, 3)
        self.assertEqual(goi, [], "lease treo -> khong duoc dung GCE")

    def test_dry_run_do_nhung_KHONG_dung_gi(self):
        lenh = []

        def _gce(l, han=300):
            lenh.append(l)
            return 0, "2026-09-04T00:00:00Z", ""

        with _vaProbe(ban_do(), dat=True), \
             mock.patch.object(pc, "gce", side_effect=_gce), \
             mock.patch.object(pc, "ghi_audit"):
            ma = pc.pha_drain(ns(dry_run=True))
        self.assertEqual(ma, 0)
        self.assertFalse(any("disable" in l for l in lenh),
                         "--dry-run khong duoc goi disable")

    def test_KHONG_BAO_GIO_terminate_hay_xoa_VM(self):
        """Cong cu nay khong duoc chua bat ky lenh huy VM nao."""
        lenh = []

        def _gce(l, han=300):
            lenh.append(l)
            return 0, "\n".join(["inactive"] * len(PROD_UNITS)), ""

        with _vaProbe(ban_do(), dat=True), \
             mock.patch.object(pc, "gce", side_effect=_gce), \
             mock.patch.object(pc, "_units_gce", return_value=units_gce(False)), \
             mock.patch.object(pc, "ghi_audit"):
            pc.pha_drain(ns())
        cam = ("instances delete", "instances stop", "terminate", "shutdown",
               "poweroff", "halt", "rm -rf", "disks delete")
        for l in lenh:
            for c in cam:
                self.assertNotIn(c, l, f"lenh nguy hiem {c!r} trong: {l[:120]}")

    def test_chi_dung_dung_ba_unit_production(self):
        lenh = []

        def _gce(l, han=300):
            lenh.append(l)
            return 0, "\n".join(["inactive"] * len(PROD_UNITS)), ""

        with _vaProbe(ban_do(), dat=True), \
             mock.patch.object(pc, "gce", side_effect=_gce), \
             mock.patch.object(pc, "_units_gce", return_value=units_gce(False)), \
             mock.patch.object(pc, "ghi_audit"):
            pc.pha_drain(ns())
        dis = [l for l in lenh if "disable" in l]
        self.assertEqual(len(dis), 1)
        for u in PROD_UNITS:
            self.assertIn(u, dis[0])
        # Khong duoc cham bat ky unit nao khac.
        self.assertNotIn("ssh", dis[0])
        self.assertNotIn("docker", dis[0])

    def test_that_bai_neu_GCE_van_con_unit_active_sau_khi_dung(self):
        with _vaProbe(ban_do(), dat=True), \
             mock.patch.object(pc, "gce", return_value=(0, "", "")), \
             mock.patch.object(pc, "_units_gce", return_value=units_gce(True)), \
             mock.patch.object(pc, "ghi_audit"):
            self.assertEqual(pc.pha_drain(ns()), 4)


class Canary(unittest.TestCase):
    """CHE DO THAT BAI SO 1: hai worker cung claim hang doi production."""

    def test_TU_CHOI_khi_GCE_van_dang_chay(self):
        goi = []
        with mock.patch.object(pc, "_units_gce", return_value=units_gce(True)), \
             mock.patch.object(pc, "cong", side_effect=lambda v, han=900: goi.append(v) or (0, "")), \
             mock.patch.object(pc, "ghi_audit"):
            ma = pc.pha_canary(ns())
        self.assertEqual(ma, 2)
        self.assertEqual(goi, [], "KHONG duoc bat AWS khi GCE con chay")

    def test_tat_staging_TRUOC_khi_bat_production(self):
        goi = []
        with mock.patch.object(pc, "_units_gce", return_value=units_gce(False)), \
             mock.patch.object(pc, "cong",
                               side_effect=lambda v, han=900: (goi.append(v), (0, "ok"))[1]), \
             mock.patch.object(pc, "ghi_audit"):
            ma = pc.pha_canary(ns())
        self.assertEqual(ma, 0)
        self.assertEqual(goi, ["stop-staging", "start", "canary"])
        self.assertLess(goi.index("stop-staging"), goi.index("start"))

    def test_start_that_bai_thi_TU_DONG_ROLLBACK(self):
        def _cong(v, han=900):
            return (3, "khong len duoc") if v == "start" else (0, "ok")

        with mock.patch.object(pc, "_units_gce", return_value=units_gce(False)), \
             mock.patch.object(pc, "cong", side_effect=_cong), \
             mock.patch.object(pc, "pha_rollback", return_value=0) as rb, \
             mock.patch.object(pc, "ghi_audit"):
            ma = pc.pha_canary(ns())
        rb.assert_called_once()
        self.assertEqual(ma, 20)

    def test_job_canary_that_bai_thi_TU_DONG_ROLLBACK(self):
        def _cong(v, han=900):
            return (6, "job khong hoan tat") if v == "canary" else (0, "ok")

        with mock.patch.object(pc, "_units_gce", return_value=units_gce(False)), \
             mock.patch.object(pc, "cong", side_effect=_cong), \
             mock.patch.object(pc, "pha_rollback", return_value=0) as rb, \
             mock.patch.object(pc, "ghi_audit"):
            ma = pc.pha_canary(ns())
        rb.assert_called_once()
        self.assertEqual(ma, 20)

    def test_rollback_that_bai_thi_bao_ma_KHAC(self):
        """Khong duoc bao cao 'da lui' khi that ra chua lui duoc."""
        def _cong(v, han=900):
            return (6, "hong") if v == "canary" else (0, "ok")

        with mock.patch.object(pc, "_units_gce", return_value=units_gce(False)), \
             mock.patch.object(pc, "cong", side_effect=_cong), \
             mock.patch.object(pc, "pha_rollback", return_value=2), \
             mock.patch.object(pc, "ghi_audit"):
            self.assertEqual(pc.pha_canary(ns()), 21)


class Observe(unittest.TestCase):
    def test_worker_ngung_active_thi_ROLLBACK(self):
        out = ("fanfic-worker-prod.service=inactive \n0\n0.1\n2000\n0\n20%\n")
        with _vaProbe(ban_do()), \
             mock.patch.object(pc, "aws", return_value=(0, out, "")), \
             mock.patch.object(pc, "_units_gce", return_value=units_gce(False)), \
             mock.patch.object(pc, "pha_rollback", return_value=0) as rb, \
             mock.patch.object(pc, "ghi_audit"):
            ma = pc.pha_observe(ns(minutes=1, every=0))
        rb.assert_called_once()
        self.assertEqual(ma, 20)

    def test_lease_treo_thi_ROLLBACK(self):
        out = ("fanfic-worker-prod.service=active \n0\n0.1\n2000\n0\n20%\n")
        with _vaProbe(ban_do(treo=1)), \
             mock.patch.object(pc, "aws", return_value=(0, out, "")), \
             mock.patch.object(pc, "_units_gce", return_value=units_gce(False)), \
             mock.patch.object(pc, "pha_rollback", return_value=0) as rb, \
             mock.patch.object(pc, "ghi_audit"):
            ma = pc.pha_observe(ns(minutes=1, every=0))
        rb.assert_called_once()
        self.assertEqual(ma, 20)

    def test_GCE_song_lai_thi_DUNG_QUAN_SAT_va_KHONG_tu_dong_lui(self):
        """F6 — mot dong doi bat lai GCE giua cua so quan sat.

        KHONG tu dong lui o day: lui nghia la bat GCE, ma GCE dang chay
        san. Hai worker dang tranh nhau; chon giu ben nao la viec cua
        nguoi, khong phai cua mot vong lap."""
        out = ("fanfic-worker-prod.service=active \n0\n0.1\n2000\n0\n20%\n")
        with _vaProbe(ban_do()), \
             mock.patch.object(pc, "aws", return_value=(0, out, "")), \
             mock.patch.object(pc, "_units_gce", return_value=units_gce(True)), \
             mock.patch.object(pc, "pha_rollback", return_value=0) as rb, \
             mock.patch.object(pc, "ghi_audit"):
            ma = pc.pha_observe(ns(minutes=1, every=0))
        self.assertEqual(ma, 5)
        rb.assert_not_called()


class Commit(unittest.TestCase):
    """CHOT chi duoc xay ra tren mot trang thai sach."""

    def test_TU_CHOI_khi_GCE_con_chay(self):
        with mock.patch.object(pc, "_units_gce", return_value=units_gce(True)), \
             mock.patch.object(pc, "_units_aws", return_value=units(active_prod=True)):
            self.assertEqual(pc.pha_commit(ns()), 2)

    def test_TU_CHOI_khi_AWS_thieu_unit(self):
        with mock.patch.object(pc, "_units_gce", return_value=units_gce(False)), \
             mock.patch.object(pc, "_units_aws", return_value=units(active_prod=False)):
            self.assertEqual(pc.pha_commit(ns()), 3)

    def test_TU_CHOI_khi_staging_tren_AWS_con_chay(self):
        with mock.patch.object(pc, "_units_gce", return_value=units_gce(False)), \
             mock.patch.object(pc, "_units_aws",
                               return_value=units(active_prod=True, active_staging=True)):
            self.assertEqual(pc.pha_commit(ns()), 4)


class RollbackDocLap(unittest.TestCase):
    """Rollback phai chay duoc ma KHONG can bat ky pha nao truoc do."""

    def test_khong_doc_tep_trang_thai_nao(self):
        import inspect
        src = inspect.getsource(pc.pha_rollback)
        for xau in ("state.json", "read_text", "json.load", "open("):
            self.assertNotIn(xau, src,
                             f"rollback khong duoc phu thuoc trang thai luu san ({xau})")

    #: Nhip that ma `--check` in ra khi vong quet dang quay.
    NHIP = '{"trang_thai": "dang_chay", "tuoi_nhip_giay": 2}'

    def test_chay_duoc_khi_cong_dieu_hanh_CHUA_cai(self):
        """Prepare that bai giua chung -> van phai lui duoc."""
        with mock.patch.object(pc, "aws", return_value=(0, "CHUA", "")), \
             mock.patch.object(pc, "gce", return_value=(0, self.NHIP, "")), \
             mock.patch.object(pc, "_units_gce", return_value=units_gce(True)), \
             mock.patch.object(pc, "_units_aws", return_value=units(active_prod=False)), \
             mock.patch.object(pc, "cong") as c, \
             mock.patch.object(pc, "ghi_audit"), \
             mock.patch.object(pc.time, "sleep"):
            ma = pc.pha_rollback(ns())
        self.assertEqual(ma, 0)
        c.assert_not_called()

    def test_bat_lai_dung_ba_unit_GCE(self):
        lenh = []

        def _gce(l, han=300):
            lenh.append(l)
            return 0, self.NHIP, ""

        with mock.patch.object(pc, "aws", return_value=(0, "CHUA", "")), \
             mock.patch.object(pc, "gce", side_effect=_gce), \
             mock.patch.object(pc, "_units_gce", return_value=units_gce(True)), \
             mock.patch.object(pc, "_units_aws", return_value=units(active_prod=False)), \
             mock.patch.object(pc, "ghi_audit"), \
             mock.patch.object(pc.time, "sleep"):
            pc.pha_rollback(ns())
        en = [l for l in lenh if "enable --now" in l]
        self.assertTrue(en)
        for u in PROD_UNITS:
            self.assertIn(u, en[0])

    def test_bao_that_bai_khi_GCE_khong_khoe_lai(self):
        with mock.patch.object(pc, "aws", return_value=(0, "CHUA", "")), \
             mock.patch.object(pc, "gce", return_value=(0, "", "")), \
             mock.patch.object(pc, "_units_gce", return_value=units_gce(False)), \
             mock.patch.object(pc, "_units_aws", return_value=units(active_prod=False)), \
             mock.patch.object(pc, "ghi_audit"), \
             mock.patch.object(pc.time, "sleep"):
            self.assertEqual(pc.pha_rollback(ns()), 2)

    def test_F10_unit_active_nhung_KHONG_co_nhip_thi_van_la_THAT_BAI(self):
        """Mot worker khoi dong duoc roi chet ngay van bao `active` vai
        giay dau. `is-active` chung minh tien trinh con song; NHIP moi
        chung minh vong quet DANG QUAY."""
        with mock.patch.object(pc, "aws", return_value=(0, "CHUA", "")), \
             mock.patch.object(pc, "gce", return_value=(0, "khong co nhip", "")), \
             mock.patch.object(pc, "_units_gce", return_value=units_gce(True)), \
             mock.patch.object(pc, "_units_aws", return_value=units(active_prod=False)), \
             mock.patch.object(pc, "ghi_audit"), \
             mock.patch.object(pc.time, "sleep"):
            self.assertEqual(pc.pha_rollback(ns()), 4)

    def test_F7_KHONG_bat_GCE_khi_AWS_chua_dung_duoc(self):
        """Bat GCE trong khi AWS van chay = hai worker claim mot hang doi."""
        with mock.patch.object(pc, "aws", return_value=(0, "CO", "")), \
             mock.patch.object(pc, "cong", return_value=(1, "stop that bai")), \
             mock.patch.object(pc, "_units_aws", return_value=units(active_prod=True)), \
             mock.patch.object(pc, "gce") as g, \
             mock.patch.object(pc, "ghi_audit"), \
             mock.patch.object(pc.time, "sleep"):
            ma = pc.pha_rollback(ns())
        self.assertEqual(ma, 3)
        g.assert_not_called()


class KhongLoBiMat(unittest.TestCase):
    def test_audit_khong_bao_gio_ghi_gia_tri_env(self):
        import inspect
        src = inspect.getsource(pc.pha_prepare)
        # `env` chi duoc di qua `tom_tat_env` va `render_env_text`.
        self.assertNotIn("ghi_audit(\"prepare.env\", env=env", src)
        self.assertIn("tom_tat_env(env)", src)

    def test_bi_mat_khong_bao_gio_qua_argv(self):
        """`aws()` nhan noi dung qua stdin, khong qua chuoi lenh."""
        import inspect
        src = inspect.getsource(pc.pha_prepare)
        self.assertIn("nhap=noi_dung", src)
        self.assertNotIn("noi_dung.decode", src)


class CongDieuHanh(unittest.TestCase):
    def test_verb_luon_duoc_trich_dan(self):
        import inspect
        self.assertIn("shlex.quote(verb)", inspect.getsource(pc.cong))



class GceKhongLienLacDuoc(unittest.TestCase):
    """LOI THAT, lo ra dung trong pha COMMIT that: `_units_gce()` tra `?`
    khi SSH hong, va ca `canary` lan `commit` chi loc `== "active"` — nen
    mot may GCE KHONG LIEN LAC DUOC di lot qua cong y het mot may da dung.

    Fail-open o dung cai cong duoc dung de CHUNG MINH GCE khong con chay.
    (Lan do that: GCE that su da dung, nen ket luan dung — nhung cong da
    khong chung minh duoc dieu do.)
    """

    KHONG_RO = {u: "?" for u in PROD_UNITS}

    def test_commit_TU_CHOI_khi_khong_doc_duoc_trang_thai_GCE(self):
        with mock.patch.object(pc, "_units_gce", return_value=dict(self.KHONG_RO)), \
             mock.patch.object(pc, "_units_aws", return_value=units(active_prod=True)), \
             mock.patch.object(pc, "ghi_audit"):
            self.assertEqual(pc.pha_commit(ns()), 7)

    def test_canary_TU_CHOI_khi_khong_doc_duoc_trang_thai_GCE(self):
        goi = []
        with mock.patch.object(pc, "_units_gce", return_value=dict(self.KHONG_RO)), \
             mock.patch.object(pc, "cong",
                               side_effect=lambda v, han=900: goi.append(v) or (0, "")), \
             mock.patch.object(pc, "ghi_audit"):
            self.assertEqual(pc.pha_canary(ns()), 6)
        self.assertEqual(goi, [], "KHONG duoc bat AWS khi chua biet GCE the nao")

    def test_mot_unit_khong_ro_cung_du_de_TU_CHOI(self):
        tt = units_gce(False)
        tt[PROD_UNITS[0]] = "?"
        with mock.patch.object(pc, "_units_gce", return_value=tt), \
             mock.patch.object(pc, "_units_aws", return_value=units(active_prod=True)), \
             mock.patch.object(pc, "ghi_audit"):
            self.assertEqual(pc.pha_commit(ns()), 7)

    def test_units_gce_thu_lai_truoc_khi_bo_cuoc(self):
        """SSH qua `gcloud` that bai chap chon la chuyen co that."""
        lan = {"n": 0}

        def _gce(l, han=300):
            lan["n"] += 1
            if lan["n"] < 3:
                return 255, "", "ssh hong"
            return 0, "\n".join(["inactive"] * len(PROD_UNITS)) + "\n---\n", ""

        with mock.patch.object(pc, "gce", side_effect=_gce), \
             mock.patch.object(pc.time, "sleep"):
            tt = pc._units_gce()
        self.assertEqual(lan["n"], 3)
        self.assertEqual(pc._gce_chua_ro(tt), [])

    def test_het_lan_thu_thi_tra_KHONG_RO(self):
        with mock.patch.object(pc, "gce", return_value=(255, "", "hong")), \
             mock.patch.object(pc.time, "sleep"):
            tt = pc._units_gce()
        self.assertEqual(len(pc._gce_chua_ro(tt)), len(PROD_UNITS))

    def test_dau_ra_thieu_dong_cung_la_KHONG_RO(self):
        """Doc duoc mot phan cung khong du de ket luan."""
        with mock.patch.object(pc, "gce", return_value=(0, "inactive\n---\n", "")), \
             mock.patch.object(pc.time, "sleep"):
            tt = pc._units_gce()
        self.assertEqual(len(pc._gce_chua_ro(tt)), len(PROD_UNITS))


class MaThoatCuaSystemctlLaMOT_PHAN_CAU_TRA_LOI(unittest.TestCase):
    """LOI THAT, chi lo ra SAU khi GCE that su dung — tuc dung luc no gay
    hai nhat.

    `systemctl is-active` thoat KHAC 0 khi unit KHONG active, va `gcloud
    compute ssh` truyen ma thoat cua lenh tu xa ra ngoai. Nen mot may GCE
    da dung DUNG NHU MONG DOI lai lam `rc != 0`, va bo doc trang thai coi
    do la "khong lien lac duoc" -> pha COMMIT tu choi vi tuong mat lien
    lac, trong khi that ra no vua doc duoc dung cai trang thai no can.
    """

    def _ra(self, trang_thai):
        return ("\n".join(trang_thai) + "\n---\n"
                + "\n".join(["disabled"] * len(PROD_UNITS)) + "\n")

    def test_doc_duoc_DU_ma_thoat_khac_0(self):
        """Day la ca bai kiem: rc != 0 nhung dau ra hop le."""
        with mock.patch.object(pc, "gce",
                               return_value=(3, self._ra(["inactive"] * len(PROD_UNITS)), "")), \
             mock.patch.object(pc.time, "sleep"):
            tt = pc._units_gce()
        self.assertEqual(pc._gce_chua_ro(tt), [])
        self.assertTrue(all(v == "inactive" for v in tt.values()))

    def test_van_doc_duoc_khi_dang_active_va_rc_bang_0(self):
        with mock.patch.object(pc, "gce",
                               return_value=(0, self._ra(["active"] * len(PROD_UNITS)), "")), \
             mock.patch.object(pc.time, "sleep"):
            tt = pc._units_gce()
        self.assertEqual(pc._gce_chua_ro(tt), [])
        self.assertTrue(all(v == "active" for v in tt.values()))

    def test_dau_ra_RAC_van_la_KHONG_RO(self):
        """Noi long ma thoat khong duoc bien thanh 'chap nhan moi thu'."""
        rac = "ERROR: (gcloud.compute.ssh) plink.exe exited with return code [1]\n"
        with mock.patch.object(pc, "gce", return_value=(1, rac, "")), \
             mock.patch.object(pc.time, "sleep"):
            tt = pc._units_gce()
        self.assertEqual(len(pc._gce_chua_ro(tt)), len(PROD_UNITS))

    def test_tu_la_khong_phai_trang_thai_systemd_thi_KHONG_RO(self):
        with mock.patch.object(pc, "gce",
                               return_value=(0, self._ra(["yes", "no", "maybe"]), "")), \
             mock.patch.object(pc.time, "sleep"):
            tt = pc._units_gce()
        self.assertEqual(len(pc._gce_chua_ro(tt)), len(PROD_UNITS))

    def test_lenh_khong_de_ma_thoat_tu_xa_lam_nhieu(self):
        lenh = []
        with mock.patch.object(pc, "gce",
                               side_effect=lambda l, han=300: (lenh.append(l), (0, "", ""))[1]), \
             mock.patch.object(pc.time, "sleep"):
            pc._units_gce(so_lan=1)
        self.assertTrue(lenh[0].rstrip().endswith("exit 0"))

if __name__ == "__main__":
    unittest.main()
